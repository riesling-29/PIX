"""Independent acceptance oracles for native HeuristicsNet conversion.

The P/T oracle implements weighted marking arithmetic itself. It never calls
PIX firing, replay, alignment, or a miner. A second oracle executes abstract
edge obligations directly for bounded acyclic and cyclic examples; neither oracle reads
conversion witness identifiers or assumes its silent-node construction.
"""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from itertools import product

import pytest

from pix.case_centric.heuristics import (
    HeuristicsActivity,
    HeuristicsBinding,
    HeuristicsNet,
    HeuristicsSpec,
    discover_heuristics,
)
from pix.case_centric.heuristics_conversion import (
    HeuristicsConversionSpec,
    heuristics_to_petri_net,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def hnet(
    activities, edges=(), *, inputs=None, outputs=None, starts=None, ends=None, empty=0
):
    """Build a model independently of discovery with consistent boundary counts."""
    activities = tuple(activities)
    edges = tuple(edges)
    starts = tuple(starts if starts is not None else activities[:1])
    ends = tuple(ends if ends is not None else activities[-1:])
    observations = len(starts) * len(ends)
    inputs = (
        inputs
        if inputs is not None
        else {a: tuple((s,) for s, t in edges if t == a) for a in activities}
    )
    outputs = (
        outputs
        if outputs is not None
        else {a: tuple((t,) for s, t in edges if s == a) for a in activities}
    )
    return HeuristicsNet(
        profile="classic",
        trace_count=observations + empty,
        empty_trace_count=empty,
        activities=tuple(
            HeuristicsActivity(
                a,
                max(2, observations * 2),
                len(ends) if a in starts else 0,
                len(starts) if a in ends else 0,
            )
            for a in activities
        ),
        follows=(),
        overlaps=(),
        dependencies=(),
        edges=edges,
        short_loops=(),
        and_pairs=(),
        bindings=tuple(
            HeuristicsBinding(a, direction, tuple(bindings.get(a, ())))
            for direction, bindings in (("input", inputs), ("output", outputs))
            for a in activities
        ),
        excluded_activities=(),
        precleaned_edges=(),
    )


def pt_language(model, max_length=7, state_limit=200_000):
    """Enumerate a bounded visible language using only P/T incidence algebra.

    Acceptance requires equality with the complete final marking, including
    the absence of every leftover edge, join, or split obligation token.
    """
    initial, final = model.initial_marking.tokens, model.final_marking.tokens
    incidences = []
    for transition in model.transitions:
        consumed = Counter()
        produced = Counter()
        for arc in model.arcs:
            if arc.target == transition.id:
                consumed[arc.source] += arc.weight
            if arc.source == transition.id:
                produced[arc.target] += arc.weight
        incidences.append((transition.activity, consumed, produced))
    pending = deque([(initial, ())])
    seen = {(initial, ())}
    accepted = set()
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.add(word)
        current = Counter(dict(marking))
        for activity, consumed, produced in incidences:
            if activity is not None and len(word) >= max_length:
                continue
            if any(current[place] < weight for place, weight in consumed.items()):
                continue
            after = current.copy()
            after.subtract(consumed)
            after.update(produced)
            state = (
                tuple(sorted((p, n) for p, n in after.items() if n)),
                word if activity is None else (*word, activity),
            )
            if state not in seen:
                seen.add(state)
                assert len(seen) <= state_limit, "independent P/T oracle bound reached"
                pending.append(state)
    return accepted


def obligation_language(net, max_length=7):
    """Atomic edge-obligation semantics with an explicit visible-length bound.

    One initial boundary ticket permits one observed start. Each occurrence
    consumes one chosen complete input set and issues one chosen output set.
    An observed end may spend that occurrence's output choice on termination;
    acceptance still requires no outstanding obligations and exactly one end.
    """
    bindings = {(row.activity, row.direction): row.alternatives for row in net.bindings}
    starts = {a.activity for a in net.activities if a.start_count}
    ends = {a.activity for a in net.activities if a.end_count}
    pending = deque([(True, 0, (), ())])
    seen = set(pending)
    accepted = {()} if net.empty_trace_count else set()
    while pending:
        start_ticket, end_tickets, frozen, word = pending.popleft()
        tokens = Counter(dict(frozen))
        if not start_ticket and end_tickets == 1 and not frozen:
            accepted.add(word)
        if len(word) >= max_length:
            continue
        for record in net.activities:
            activity = record.activity
            in_choices = [
                (members, False) for members in bindings.get((activity, "input"), ())
            ]
            if activity in starts and start_ticket:
                in_choices.append(((), True))
            out_choices = [
                (members, False) for members in bindings.get((activity, "output"), ())
            ]
            if activity in ends:
                out_choices.append(((), True))
            for (incoming, starts_now), (outgoing, ends_now) in product(
                in_choices, out_choices
            ):
                if any(tokens[pred, activity] < 1 for pred in incoming):
                    continue
                after = tokens.copy()
                for predecessor in incoming:
                    after[predecessor, activity] -= 1
                for successor in outgoing:
                    after[activity, successor] += 1
                state = (
                    start_ticket and not starts_now,
                    end_tickets + int(ends_now),
                    tuple(sorted((edge, n) for edge, n in after.items() if n)),
                    (*word, activity),
                )
                if state not in seen:
                    seen.add(state)
                    pending.append(state)
    return accepted


def converted(net, spec=HeuristicsConversionSpec()):
    result = heuristics_to_petri_net(net, spec)
    assert result.status is ComputeStatus.COMPUTED, result.issues
    assert result.value is not None
    return result


def test_sequence_has_only_its_hand_specified_word():
    model = converted(hnet("abcd", (("a", "b"), ("b", "c"), ("c", "d")))).value.model
    assert pt_language(model) == {tuple("abcd")}


def test_xor_branch_does_not_require_both_alternatives():
    net = hnet("abcd", (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")))
    assert pt_language(converted(net).value.model) == {tuple("abd"), tuple("acd")}


def test_and_branch_requires_both_orders_and_no_shortcut():
    net = hnet(
        "abcd",
        (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")),
        inputs={"b": (("a",),), "c": (("a",),), "d": (("b", "c"),)},
        outputs={"a": (("b", "c"),), "b": (("d",),), "c": (("d",),)},
    )
    assert pt_language(converted(net).value.model) == {tuple("abcd"), tuple("acbd")}


def test_mixed_or_of_and_bindings_preserves_group_membership():
    net = hnet(
        "abcde",
        (("a", "b"), ("a", "c"), ("a", "d"), ("b", "e"), ("c", "e"), ("d", "e")),
        inputs={
            "b": (("a",),),
            "c": (("a",),),
            "d": (("a",),),
            "e": (("b", "c"), ("d",)),
        },
        outputs={
            "a": (("b", "c"), ("d",)),
            "b": (("e",),),
            "c": (("e",),),
            "d": (("e",),),
        },
    )
    assert pt_language(converted(net).value.model) == {
        tuple("abce"),
        tuple("acbe"),
        tuple("ade"),
    }


def test_final_sink_token_with_leftover_obligations_is_not_accepting():
    # a creates both branches, whereas d consumes just one. Completing d once
    # leaves a branch; completing it twice leaves two end tokens. Neither fits.
    net = hnet(
        "abcd",
        (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")),
        outputs={"a": (("b", "c"),), "b": (("d",),), "c": (("d",),)},
    )
    assert pt_language(converted(net).value.model) == set()


def test_boundary_start_is_exclusive_and_not_an_and_split():
    net = hnet("ab", starts="ab", ends="ab")
    assert pt_language(converted(net).value.model) == {("a",), ("b",)}


def test_end_choice_does_not_force_an_observed_end_to_always_stop():
    # a is both an observed end and a predecessor of another observed end.
    net = hnet("ab", (("a", "b"),), starts="a", ends="ab")
    assert pt_language(converted(net).value.model) == {("a",), ("a", "b")}


def test_cycle_uses_start_boundary_separately_from_reentry_binding():
    net = hnet("abc", (("a", "b"), ("b", "a"), ("a", "c")))
    assert pt_language(converted(net).value.model, max_length=8) == {
        tuple("a" + "ba" * count + "c") for count in range(4)
    }


def test_explicit_self_loop_accepts_nonempty_repetition_without_epsilon():
    net = hnet("a", (("a", "a"),))
    assert pt_language(converted(net).value.model, max_length=5) == {
        ("a",) * count for count in range(1, 6)
    }


@pytest.mark.parametrize("missing_direction", ["input", "output", "both"])
def test_self_loop_without_explicit_bindings_is_unavailable(missing_direction):
    net = hnet("a", (("a", "a"),))
    net = replace(
        net,
        bindings=tuple(
            replace(b, alternatives=())
            if missing_direction in ("both", b.direction)
            else b
            for b in net.bindings
        ),
    )
    result = heuristics_to_petri_net(net)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "heuristics_self_loop_binding_missing" in {
        issue.code for issue in result.issues
    }


def test_epsilon_is_added_only_by_observed_empty_trace_evidence():
    net = hnet("ab", (("a", "b"),), empty=1)
    assert pt_language(converted(net).value.model) == {(), ("a", "b")}
    assert pt_language(converted(hnet((), empty=2)).value.model) == {()}
    no_evidence = heuristics_to_petri_net(hnet(()))
    assert no_evidence.status is ComputeStatus.UNAVAILABLE
    assert no_evidence.value is None


@pytest.mark.parametrize("direction", ["start_count", "end_count"])
def test_nonempty_model_with_unknown_observed_boundary_is_unavailable(direction):
    net = hnet("ab", (("a", "b"),))
    net = replace(
        net, activities=tuple(replace(a, **{direction: 0}) for a in net.activities)
    )
    result = heuristics_to_petri_net(net)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


# Every nonempty family of nonempty subsets that covers {b,c}: XOR, AND,
# singleton plus AND (two forms), and inclusive choice of all three sets.
FULL_COVER_BINDINGS = (
    (("b",), ("c",)),
    (("b", "c"),),
    (("b",), ("b", "c")),
    (("c",), ("b", "c")),
    (("b",), ("c",), ("b", "c")),
)


@pytest.mark.parametrize(
    "out_choices,in_choices", tuple(product(FULL_COVER_BINDINGS, repeat=2))
)
def test_exhaustive_small_branch_bindings_against_obligation_oracle(
    out_choices, in_choices
):
    net = hnet(
        "abcd",
        (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")),
        inputs={"b": (("a",),), "c": (("a",),), "d": in_choices},
        outputs={"a": out_choices, "b": (("d",),), "c": (("d",),)},
    )
    actual = pt_language(converted(net).value.model, max_length=5)
    expected = obligation_language(net, max_length=5)
    assert actual == expected


def test_mixed_cycle_and_bindings_match_atomic_obligations_with_repeated_activity():
    # a can issue b alone or b AND c; b either re-enters a or feeds the end.
    # c obligations can survive several a/b occurrences, so single-visit or
    # set-valued approximations cannot substitute for token multiplicities.
    net = hnet(
        "abcd",
        (("a", "b"), ("a", "c"), ("b", "a"), ("b", "d"), ("c", "d")),
        inputs={
            "a": (("b",),),
            "b": (("a",),),
            "c": (("a",),),
            "d": (("b",), ("b", "c")),
        },
        outputs={"a": (("b",), ("b", "c")), "b": (("a",), ("d",)), "c": (("d",),)},
    )
    expected = obligation_language(net, max_length=7)
    assert {
        tuple(word) for word in ("abd", "abcd", "acbd", "ababd", "ababcd")
    } <= expected
    assert pt_language(converted(net).value.model, max_length=7) == expected


def test_witnesses_link_each_activity_edge_and_binding_to_real_nodes():
    net = hnet("abcd", (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")))
    value = converted(net).value
    assert value.profile == "pix.heuristics.bindings.v1"
    assert isinstance(value.source_model_digest, str) and value.source_model_digest
    transition_labels = {t.id: t.activity for t in value.model.transitions}
    assert dict(value.activity_transitions).keys() == set("abcd")
    for activity, transition in value.activity_transitions:
        assert transition_labels[transition] == activity
    assert Counter(
        t.activity for t in value.model.transitions if t.activity is not None
    ) == Counter("abcd")
    assert {(p.source, p.target) for p in value.edge_places} == set(net.edges)
    assert len({p.place_id for p in value.edge_places}) == len(net.edges)
    assert {p.place_id for p in value.edge_places} <= {p.id for p in value.model.places}
    actual_bindings = {
        (b.activity, b.direction, frozenset(b.members))
        for b in value.binding_transitions
    }
    expected_bindings = {
        (b.activity, b.direction, frozenset(members))
        for b in net.bindings
        for members in b.alternatives
    }
    expected_bindings |= {("a", "start", frozenset()), ("d", "end", frozenset())}
    assert actual_bindings == expected_bindings
    for binding in value.binding_transitions:
        assert transition_labels[binding.transition_id] is None
    with pytest.raises(FrozenInstanceError):
        value.profile = "changed"


def test_activity_labels_cannot_collide_with_generated_node_identifiers():
    labels = ("source", "sink", "τ", "hn:edge:a:b", "a/b")
    net = hnet(labels, tuple(zip(labels, labels[1:])))
    value = converted(net).value
    assert pt_language(value.model) == {labels}
    ids = [p.id for p in value.model.places] + [t.id for t in value.model.transitions]
    assert len(ids) == len(set(ids))


def test_repeated_conversion_is_deterministic_and_does_not_mutate_source():
    net = hnet("abc", (("a", "b"), ("b", "c")))
    before = repr(net)
    one, two = converted(net), converted(net)
    assert one == two
    assert repr(net) == before
    assert one.computation_id and one.source_digest


def test_reordering_setlike_model_fields_preserves_the_executable_model():
    raw = hnet(
        "abcd",
        (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")),
        inputs={"b": (("a",),), "c": (("a",),), "d": (("b", "c"),)},
        outputs={"a": (("b", "c"),), "b": (("d",),), "c": (("d",),)},
    )
    changed = replace(
        raw,
        activities=raw.activities[::-1],
        edges=raw.edges[::-1],
        bindings=tuple(
            replace(
                b, alternatives=tuple(members[::-1] for members in b.alternatives[::-1])
            )
            for b in raw.bindings[::-1]
        ),
    )
    one, two = converted(raw).value, converted(changed).value
    assert one.model == two.model
    assert one.activity_transitions == two.activity_transitions
    assert one.binding_transitions == two.binding_transitions
    # Source identity records the full typed input, including tuple order.
    assert one.source_model_digest != two.source_model_digest


def test_frequency_is_evidence_not_an_arc_token_weight():
    raw = hnet("ab", (("a", "b"),))
    repeated = replace(
        raw,
        trace_count=7,
        activities=tuple(
            replace(
                a, count=14, start_count=a.start_count * 7, end_count=a.end_count * 7
            )
            for a in raw.activities
        ),
    )
    one, two = converted(raw), converted(repeated)
    assert one.value.model == two.value.model
    assert all(arc.weight == 1 for arc in two.value.model.arcs)
    assert one.computation_id != two.computation_id


def case_log(word):
    return CaseLog(
        (
            CaseTrace(
                "case-1",
                tuple(
                    CaseEvent(
                        f"event-{index}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for index, activity in enumerate(word)
                ),
            ),
        )
    )


def test_actual_miner_sequence_converts_with_observed_source_and_parent_evidence():
    mined = discover_heuristics(case_log("abcd"))
    assert mined.status is ComputeStatus.COMPUTED
    result = converted(mined)
    assert pt_language(result.value.model) == {tuple("abcd")}
    assert result.source_digest == mined.source_digest
    assert result.parent_computation_ids == (mined.computation_id,)
    assert all(issue in result.issues for issue in mined.issues)


def test_actual_miner_selfedge_gap_is_not_silently_completed_or_discarded():
    mined = discover_heuristics(case_log("aab"))
    assert mined.status is ComputeStatus.COMPUTED
    assert ("a", "a") in mined.value.edges
    result = heuristics_to_petri_net(mined)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "heuristics_self_loop_binding_missing" in {
        issue.code for issue in result.issues
    }
    assert result.source_digest == mined.source_digest
    assert result.parent_computation_ids == (mined.computation_id,)


def parent_result(net, status=ComputeStatus.COMPUTED):
    return ComputationResult(
        operator_id="test.independent.heuristics",
        operator_version="1.0.0",
        source_digest="independent-source-digest",
        spec=HeuristicsSpec(),
        status=status,
        value=net
        if status in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL)
        else None,
        issues=(
            ComputeIssue("parent_witness", "Upstream evidence must survive conversion"),
        ),
        computation_id="independent-parent-request-id",
    )


def test_parent_provenance_and_issues_survive_conversion():
    raw = hnet("ab", (("a", "b"),))
    parent = parent_result(raw)
    result = converted(parent)
    assert result.source_digest == parent.source_digest
    assert result.parent_computation_ids == (parent.computation_id,)
    assert parent.issues[0] in result.issues
    assert result.value == converted(raw).value


def test_different_model_under_same_parent_cannot_have_same_request_identity():
    raw = hnet("ab", (("a", "b"),))
    changed = replace(raw, empty_trace_count=1, trace_count=raw.trace_count + 1)
    one = converted(parent_result(raw))
    two = converted(parent_result(changed))
    assert one.parent_computation_ids == two.parent_computation_ids
    assert one.source_digest == two.source_digest
    assert one.computation_id != two.computation_id
    assert one.value.source_model_digest != two.value.source_model_digest
    assert pt_language(one.value.model) != pt_language(two.value.model)


@pytest.mark.parametrize(
    "status",
    [ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE, ComputeStatus.INVALID_INPUT],
)
def test_incomplete_parent_cannot_be_upgraded_to_a_complete_model(status):
    parent = parent_result(hnet("a"), status)
    result = heuristics_to_petri_net(parent)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert parent.issues[0] in result.issues
    assert result.parent_computation_ids == (parent.computation_id,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_net_nodes", 0),
        ("max_net_nodes", -1),
        ("max_net_nodes", True),
        ("max_net_nodes", 1.5),
        ("max_net_arcs", 0),
        ("max_net_arcs", False),
        ("max_net_arcs", "10"),
    ],
)
def test_resource_specs_require_positive_integers(field, value):
    with pytest.raises((TypeError, ValueError)):
        HeuristicsConversionSpec(**{field: value})


@pytest.mark.parametrize("field", ["max_net_nodes", "max_net_arcs"])
def test_exact_resource_boundary_succeeds_one_below_returns_no_truncated_net(field):
    net = hnet("abc", (("a", "b"), ("b", "c")))
    normal = converted(net).value.model
    exact_count = (
        len(normal.places) + len(normal.transitions)
        if field == "max_net_nodes"
        else len(normal.arcs)
    )
    exact = converted(net, HeuristicsConversionSpec(**{field: exact_count}))
    assert exact.value.model == normal
    limited = heuristics_to_petri_net(
        net, HeuristicsConversionSpec(**{field: exact_count - 1})
    )
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None
    assert limited.issues


def malformed_models():
    base = hnet("ab", (("a", "b"),))
    first = base.activities[0]

    def binding_change(**changes):
        return replace(
            base,
            bindings=tuple(
                replace(b, **changes)
                if (b.activity, b.direction) == ("a", "output")
                else b
                for b in base.bindings
            ),
        )

    yield "unknown_edge", replace(base, edges=((*base.edges, ("a", "z"))))
    yield "duplicate_edge", replace(base, edges=base.edges * 2)
    yield (
        "unknown_binding_activity",
        replace(
            base, bindings=(*base.bindings, HeuristicsBinding("z", "input", (("a",),)))
        ),
    )
    yield "unknown_binding_member", binding_change(alternatives=(("z",),))
    yield "duplicate_activity", replace(base, activities=(*base.activities, first))
    yield "duplicate_binding", replace(base, bindings=base.bindings * 2)
    yield "duplicate_alternative", binding_change(alternatives=(("b",), ("b",)))
    yield "duplicate_member", binding_change(alternatives=(("b", "b"),))
    yield "empty_alternative", binding_change(alternatives=((),))
    yield "wrong_direction", binding_change(direction="both")
    yield (
        "missing_input_coverage",
        replace(
            base,
            bindings=tuple(
                replace(b, alternatives=()) if b.direction == "input" else b
                for b in base.bindings
            ),
        ),
    )
    yield "missing_output_coverage", binding_change(alternatives=())
    yield "binding_without_edge", replace(base, edges=())
    yield "negative_trace_count", replace(base, trace_count=-1)
    yield "bool_trace_count", replace(base, trace_count=True)
    yield (
        "empty_larger_than_total",
        replace(base, empty_trace_count=base.trace_count + 1),
    )
    yield (
        "negative_activity_count",
        replace(base, activities=(replace(first, count=-1), *base.activities[1:])),
    )
    yield (
        "start_larger_than_activity",
        replace(
            base,
            activities=(
                replace(first, start_count=first.count + 1),
                *base.activities[1:],
            ),
        ),
    )
    yield (
        "negative_end_count",
        replace(base, activities=(replace(first, end_count=-1), *base.activities[1:])),
    )


@pytest.mark.parametrize(
    "name,net",
    tuple(malformed_models()),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_malformed_models_are_rejected_without_a_net(name, net):
    result = heuristics_to_petri_net(net)
    assert result.status is ComputeStatus.INVALID_INPUT, (name, result.issues)
    assert result.value is None
    assert result.issues
