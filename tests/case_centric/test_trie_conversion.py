"""Finite-language oracle uses independent incidence arithmetic, not PIX firing."""

from collections import Counter, deque
from dataclasses import replace
from itertools import combinations

import pytest

from pix.case_centric.discovery import (
    PrefixTreeSpec,
    StateEdge,
    StateNode,
    TransitionSystem,
    TransitionSystemSpec,
    discover_prefix_tree,
    discover_transition_system,
)
from pix.case_centric.trie_conversion import (
    RESULT_SCHEMAS,
    TrieConversionSpec,
    trie_to_petri_net,
)
from pix.contracts.models import Arc, Marking
from pix.contracts.result import ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log_of(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"case:{i}",
                tuple(
                    CaseEvent(
                        f"event:{i}:{j}", (CaseAttribute("concept:name", "string", a),)
                    )
                    for j, a in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def trie_of(*words):
    """Hand specification of the already existing TransitionSystem contract."""
    prefixes = {word[:i] for word in words for i in range(len(word) + 1)}
    prefixes = sorted(prefixes)
    ids = {p: f"source-state-{i}" for i, p in enumerate(prefixes)}
    visits = {p: sum(w[: len(p)] == p for w in words) for p in prefixes}
    terminals = Counter(words)
    states = tuple(
        StateNode(ids[p], p, visits[p], len(words) if not p else 0, terminals[p])
        for p in prefixes
    )
    edges = tuple(
        StateEdge(ids[p[:-1]], ids[p], p[-1], visits[p]) for p in prefixes if p
    )
    return TransitionSystem(states, edges, len(words), True)


def accepted_words(net):
    """Explore every marking/word; oracle knows no converter-generated IDs."""
    incidence = []
    for transition in net.transitions:
        consumed = Counter(
            {a.source: a.weight for a in net.arcs if a.target == transition.id}
        )
        produced = Counter(
            {a.target: a.weight for a in net.arcs if a.source == transition.id}
        )
        incidence.append((transition.activity, consumed, produced))
    initial = (net.initial_marking.tokens, ())
    queue, seen, accepted = deque([initial]), {initial}, set()
    while queue:
        marking, word = queue.popleft()
        assert sum(n for _, n in marking) == 1  # independent safety check
        if marking == net.final_marking.tokens:
            accepted.add(word)
        tokens = Counter(dict(marking))
        for activity, consume, produce in incidence:
            if any(tokens[p] < n for p, n in consume.items()):
                continue
            following = tokens.copy()
            following.subtract(consume)
            following.update(produce)
            state = (
                tuple(sorted((p, n) for p, n in following.items() if n)),
                word if activity is None else (*word, activity),
            )
            if state not in seen:
                seen.add(state)
                assert len(seen) < 1_000, "independent oracle guard exceeded"
                queue.append(state)
    return accepted


@pytest.mark.parametrize(
    "words",
    [
        ((),),
        ((), ()),
        (("A",),),
        (("A",), ("A", "B")),
        (("A", "B"), ("A", "C")),
        (("A", "A", "A"),),
        (("A", "B"), ("C", "B")),
        ((), ("A", "B"), ("A", "B"), ("B", "A")),
        (("시작", "검토", "검토"), ("시작", "완료")),
        (("trie:p:sink", "trie:t:edge:0"), ("trie:p:sink",)),
    ],
)
def test_exact_finite_language_and_frequency_evidence(words):
    result = trie_to_petri_net(trie_of(*words))
    assert result.status is ComputeStatus.COMPUTED, result.issues
    value = result.value
    assert accepted_words(value.model) == set(words)
    assert value.trace_count == len(words)
    assert value.allows_empty_trace == (() in words)
    assert sum(r.final_count for r in value.terminal_mappings) == len(words)
    assert {
        r.context: r.final_count for r in value.state_mappings if r.final_count
    } == dict(Counter(words))
    assert all(arc.weight == 1 for arc in value.model.arcs)


def test_all_small_finite_languages_preserve_terminal_not_just_prefix_acceptance():
    universe = ((), ("A",), ("B",), ("A", "A"), ("A", "B"), ("B", "A"))
    for size in range(1, len(universe) + 1):
        for words in combinations(universe, size):
            result = trie_to_petri_net(trie_of(*words))
            assert result.status is ComputeStatus.COMPUTED
            assert accepted_words(result.value.model) == set(words)


def test_repeated_activity_occurrences_get_distinct_transition_mapping():
    source = trie_of(("A", "B"), ("C", "B"), ("A", "A"))
    value = trie_to_petri_net(source).value
    b_edges = [e for e in value.edge_mappings if e.activity == "B"]
    a_edges = [e for e in value.edge_mappings if e.activity == "A"]
    assert len({e.transition_id for e in b_edges}) == 2
    assert len({e.transition_id for e in a_edges}) == 2
    assert {
        (e.source_state_id, e.target_state_id, e.activity, e.occurrence_count)
        for e in value.edge_mappings
    } == {
        (e.source, e.target, e.activity, e.occurrence_count) for e in source.transitions
    }
    assert {s.state_id for s in value.state_mappings} == {s.id for s in source.states}


def test_discovery_pipeline_keeps_source_parent_and_model_identities():
    discovered = discover_prefix_tree(log_of("AB", "A", ""))
    converted = trie_to_petri_net(discovered)
    assert converted.status is ComputeStatus.COMPUTED
    assert converted.source_digest == discovered.source_digest
    assert converted.parent_computation_ids == (discovered.computation_id,)
    assert converted.spec.model_digest == converted.value.source_model_digest
    assert accepted_words(converted.value.model) == {(), ("A",), ("A", "B")}
    assert (
        converted.computation_id != trie_to_petri_net(discovered.value).computation_id
    )
    assert (
        converted.computation_id
        != trie_to_petri_net(
            discovered, TrieConversionSpec(max_net_nodes=999)
        ).computation_id
    )


def test_full_past_sequence_ts_allowed_but_windowed_ts_rejected():
    log = log_of("ABA", "AB")
    full = discover_transition_system(log, TransitionSystemSpec(window=None))
    assert trie_to_petri_net(full).status is ComputeStatus.COMPUTED
    windowed = discover_transition_system(log, TransitionSystemSpec(window=1))
    assert trie_to_petri_net(windowed).status is ComputeStatus.INVALID_INPUT


def test_empty_log_is_not_epsilon():
    for source in (trie_of(), discover_prefix_tree(log_of())):
        result = trie_to_petri_net(source)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
        assert result.issues[-1].code == "trie_empty_log"


def test_partial_input_never_emits_truncated_language():
    parent = discover_prefix_tree(log_of("AB", "CD"), PrefixTreeSpec(max_states=3))
    assert parent.status is ComputeStatus.PARTIAL
    for source in (parent, parent.value):
        result = trie_to_petri_net(source)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None


def test_output_limits_at_exact_boundary():
    source = trie_of(("A",), ("A", "B"))
    baseline = trie_to_petri_net(source).value.model
    nodes = len(baseline.places) + len(baseline.transitions)
    arcs = len(baseline.arcs)
    assert (
        trie_to_petri_net(source, TrieConversionSpec(nodes, arcs)).status
        is ComputeStatus.COMPUTED
    )
    for spec in (
        TrieConversionSpec(nodes - 1, arcs),
        TrieConversionSpec(nodes, arcs - 1),
    ):
        result = trie_to_petri_net(source, spec)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
        assert result.issues[-1].code == "trie_conversion_limit"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: replace(g, trace_count=True),
        lambda g: replace(g, complete="yes"),
        lambda g: replace(g, states=list(g.states)),
        lambda g: replace(g, transitions=list(g.transitions)),
        lambda g: replace(g, states=g.states + (g.states[0],)),
        lambda g: replace(g, states=(replace(g.states[0], id=" "), *g.states[1:])),
        lambda g: replace(
            g, states=(replace(g.states[0], initial_count=0), *g.states[1:])
        ),
        lambda g: replace(
            g, states=(replace(g.states[0], final_count=1), *g.states[1:])
        ),
        lambda g: replace(g, states=(*g.states[:-1], replace(g.states[-1], visits=99))),
        lambda g: replace(
            g, states=(*g.states[:-1], replace(g.states[-1], context=("B", "A")))
        ),
        lambda g: replace(g, transitions=g.transitions + (g.transitions[0],)),
        lambda g: replace(g, transitions=g.transitions[:-1]),
        lambda g: replace(
            g, transitions=(replace(g.transitions[0], activity="B"), *g.transitions[1:])
        ),
        lambda g: replace(
            g,
            transitions=(
                replace(g.transitions[0], target="missing"),
                *g.transitions[1:],
            ),
        ),
        lambda g: replace(
            g,
            transitions=(
                replace(g.transitions[0], occurrence_count=2),
                *g.transitions[1:],
            ),
        ),
        lambda g: replace(
            g,
            transitions=(
                replace(g.transitions[0], occurrence_count=True),
                *g.transitions[1:],
            ),
        ),
    ],
)
def test_malformed_prefix_or_frequency_input_is_invalid(mutate):
    result = trie_to_petri_net(mutate(trie_of(("A", "B"))))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[-1].code == "invalid_trie"


def test_wrong_input_types_and_wrong_parent_payload():
    with pytest.raises(TypeError):
        trie_to_petri_net(object())
    with pytest.raises(TypeError):
        trie_to_petri_net(trie_of(("A",)), object())
    discovered = discover_prefix_tree(log_of("A"))
    result = trie_to_petri_net(replace(discovered, value=("not a trie",)))
    assert result.status is ComputeStatus.INVALID_INPUT


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_net_nodes": True},
        {"max_net_nodes": 0},
        {"max_net_nodes": 1.5},
        {"max_net_arcs": 0},
        {"max_net_arcs": -1},
    ],
)
def test_bad_spec_limits(kwargs):
    with pytest.raises(ValueError):
        TrieConversionSpec(**kwargs)


def test_evidence_cannot_claim_different_acceptance_or_transition_mapping():
    value = trie_to_petri_net(trie_of(("A",), ("A", "B"))).value
    with pytest.raises(ValueError, match="epsilon"):
        replace(value, allows_empty_trace=True)
    with pytest.raises(ValueError, match="terminal mappings"):
        replace(value, terminal_mappings=value.terminal_mappings[:-1])
    with pytest.raises(ValueError, match="terminal frequency"):
        replace(
            value,
            terminal_mappings=(
                replace(value.terminal_mappings[0], final_count=9),
                *value.terminal_mappings[1:],
            ),
        )
    with pytest.raises(ValueError, match="transitions differ"):
        replace(
            value,
            edge_mappings=(
                replace(value.edge_mappings[0], transition_id="forged"),
                *value.edge_mappings[1:],
            ),
        )
    with pytest.raises(ValueError, match="initial marking"):
        replace(value, model=replace(value.model, initial_marking=Marking()))
    first, *rest = value.model.arcs
    with pytest.raises(ValueError, match="arcs differ"):
        replace(
            value,
            model=replace(
                value.model, arcs=(Arc(first.source, first.target, 2), *rest)
            ),
        )


def test_source_order_preserved_in_evidence_and_artifact_identity_but_not_net():
    from pix.models import model_document

    source = trie_of(("A", "A"), ("A", "B"), ("B",))
    reversed_source = replace(
        source,
        states=tuple(reversed(source.states)),
        transitions=tuple(reversed(source.transitions)),
    )
    first, second = (
        trie_to_petri_net(source).value,
        trie_to_petri_net(reversed_source).value,
    )
    assert first.model == second.model
    assert first.state_mappings == tuple(reversed(second.state_mappings))
    assert first.edge_mappings == tuple(reversed(second.edge_mappings))
    assert first.source_model_digest == model_document(source)["model_digest"]
    assert second.source_model_digest == model_document(reversed_source)["model_digest"]


def test_consistent_frequency_forgery_cannot_keep_original_model_digest():
    value = trie_to_petri_net(trie_of(("A",))).value
    with pytest.raises(ValueError, match="source model digest"):
        replace(
            value,
            state_mappings=tuple(
                replace(
                    r,
                    visits=r.visits * 2,
                    initial_count=r.initial_count * 2,
                    final_count=r.final_count * 2,
                )
                for r in value.state_mappings
            ),
            edge_mappings=tuple(
                replace(r, occurrence_count=r.occurrence_count * 2)
                for r in value.edge_mappings
            ),
            terminal_mappings=tuple(
                replace(r, final_count=r.final_count * 2)
                for r in value.terminal_mappings
            ),
            trace_count=value.trace_count * 2,
        )


def test_public_result_artifact_roundtrip_and_request_digest_mismatch():
    from pix.results import result_from_json, result_json_bytes

    for source in (
        trie_of(("A",)),
        trie_of((), ("A", "B")),
        trie_of(),
        discover_prefix_tree(log_of("A", "AB", "")),
    ):
        result = trie_to_petri_net(source)
        encoded = result_json_bytes(result)
        restored = result_from_json(encoded)
        assert restored == result
        assert result_json_bytes(restored) == encoded
    first = trie_to_petri_net(trie_of(("A",)))
    second = trie_to_petri_net(trie_of(("A",), ("A",)))
    with pytest.raises(ValueError, match="model digests disagree"):
        result_json_bytes(replace(first, value=second.value))


def test_result_schema_declares_native_types():
    result = trie_to_petri_net(trie_of(("A",)))
    _, request_type, value_type = RESULT_SCHEMAS[result.operator_id]
    assert isinstance(result.spec, request_type)
    assert isinstance(result.value, value_type)
