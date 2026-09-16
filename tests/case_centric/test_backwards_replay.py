"""Native backwards replay checked against independent forward token equations."""

import random
from collections import deque
from dataclasses import FrozenInstanceError, replace

import pytest

from pix.case_centric.backwards_replay import (
    RESULT_SCHEMAS,
    BackwardsReplayRequest,
    BackwardsReplaySet,
    BackwardsReplaySpec,
    replay_backwards,
)
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.replay import TokenCounts
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(
                        f"{i}-{j}", (CaseAttribute("concept:name", "string", activity),)
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def net(places, transitions, arcs, initial, final):
    return PetriNet(
        tuple(Place(place) for place in places),
        tuple(Transition(*transition) for transition in transitions),
        tuple(Arc(*arc) for arc in arcs),
        Marking(tuple(initial)),
        Marking(tuple(final)),
    )


def sequence():
    return net(
        ("p", "q", "f"),
        (("a", "A"), ("b", "B")),
        (("p", "a"), ("a", "q"), ("q", "b"), ("b", "f")),
        (("p", 1),),
        (("f", 1),),
    )


def ids(case):
    return tuple(
        step.transition_id for step in case.steps if step.transition_id is not None
    )


def incidence(model, transition_id):
    inputs = {
        arc.source: arc.weight for arc in model.arcs if arc.target == transition_id
    }
    outputs = {
        arc.target: arc.weight for arc in model.arcs if arc.source == transition_id
    }
    return inputs, outputs


def direct_fire(model, marking, transition_id):
    inputs, outputs = incidence(model, transition_id)
    if any(marking.get(place, 0) < amount for place, amount in inputs.items()):
        return None
    after = dict(marking)
    for place, amount in inputs.items():
        after[place] -= amount
    for place, amount in outputs.items():
        after[place] = after.get(place, 0) + amount
    return {place: amount for place, amount in after.items() if amount}


def forward_oracle(model, marking, activity=None):
    """Exhaust concrete silent reachability; fixtures have conserved token totals."""
    initial = tuple(sorted(marking.items()))
    queue, visited = deque(((initial, ()),)), {initial}
    visible = tuple(t.id for t in model.transitions if t.activity == activity)
    silent = tuple(t.id for t in model.transitions if t.activity is None)
    while queue:
        state, path = queue.popleft()
        current = dict(state)
        if activity is None:
            if current == dict(model.final_marking.tokens):
                return path, None, current
        else:
            for target in visible:
                if direct_fire(model, current, target) is not None:
                    return path, target, current
        for transition_id in silent:
            after = direct_fire(model, current, transition_id)
            if after is None:
                continue
            key = tuple(sorted(after.items()))
            if key not in visited:
                visited.add(key)
                queue.append((key, path + (transition_id,)))
    return None


def check_evidence(model, case):
    """Verify each forward step and each backward equation without PIX helpers."""
    current = {}
    missing = consumed = produced = 0
    for step in case.steps:
        assert current == dict(step.marking_before)
        repaired = dict(current)
        for place, amount in step.inserted_tokens:
            repaired[place] = repaired.get(place, 0) + amount
            missing += amount
        if step.transition_id is not None:
            after = direct_fire(model, repaired, step.transition_id)
            assert after is not None
            inputs, outputs = incidence(model, step.transition_id)
            assert dict(step.consumed_tokens) == inputs
            assert dict(step.produced_tokens) == outputs
        else:
            after = repaired
            for place, amount in step.consumed_tokens:
                after[place] -= amount
            for place, amount in step.produced_tokens:
                after[place] = after.get(place, 0) + amount
            after = {place: amount for place, amount in after.items() if amount}
        assert after == dict(step.marking_after)
        consumed += sum(amount for _, amount in step.consumed_tokens)
        produced += sum(amount for _, amount in step.produced_tokens)
        current = after
    assert current == dict(case.ending_marking)
    assert case.counts == TokenCounts(
        missing, sum(current.values()), consumed, produced
    )
    assert produced + missing == consumed + sum(current.values())
    for search in case.searches:
        requirement = dict(search.target_marking)
        for regression in search.regressions:
            assert dict(regression.required_after) == requirement
            pre, post = incidence(model, regression.transition_id)
            before = dict(regression.required_before)
            for place in set(pre) | set(post) | set(requirement) | set(before):
                expected = pre.get(place, 0) + max(
                    requirement.get(place, 0) - post.get(place, 0), 0
                )
                assert before.get(place, 0) == expected
            if search.mode == "exact_final":
                assert (
                    direct_fire(model, before, regression.transition_id) == requirement
                )
            else:
                after = direct_fire(model, before, regression.transition_id)
                assert after is not None
                assert all(
                    after.get(place, 0) >= amount
                    for place, amount in requirement.items()
                )
            requirement = before


def test_direct_sequence_counts_and_event_identity():
    model = sequence()
    result = replay_backwards(log("AB"), model)
    case = result.value.traces[0]
    assert result.status is ComputeStatus.COMPUTED
    assert ids(case) == ("a", "b")
    assert case.counts == TokenCounts(0, 0, 3, 3)
    assert case.final_reached is True
    assert tuple(step.event_id for step in case.steps if step.kind == "visible") == (
        "0-0",
        "0-1",
    )
    check_evidence(model, case)


def test_backward_plan_joins_independent_silent_producers():
    model = net(
        ("p", "q", "r", "f"),
        (("a", None), ("b", None), ("v", "A")),
        (
            ("p", "a"),
            ("a", "q"),
            ("p", "b"),
            ("b", "r"),
            ("q", "v"),
            ("r", "v"),
            ("v", "f"),
        ),
        (("p", 2),),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("a", "b", "v")
    assert case.counts == TokenCounts(0, 0, 5, 5)
    assert tuple(item.transition_id for item in case.searches[0].regressions) == (
        "b",
        "a",
    )
    check_evidence(model, case)


def test_repeated_silent_growth_and_weighted_requirement():
    model = net(
        ("p", "f"),
        (("g", None), ("v", "A")),
        (("p", "g"), ("g", "p", 2), ("p", "v", 3), ("v", "f")),
        (("p", 1),),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("g", "g", "v")
    assert case.counts == TokenCounts(0, 0, 6, 6)
    check_evidence(model, case)


def test_weighted_residual_tokens_are_preserved_during_regression():
    model = net(
        ("s", "q", "f"),
        (("t", None), ("v", "A")),
        (("s", "t", 2), ("t", "q", 2), ("q", "v", 3), ("v", "f")),
        (("s", 2), ("q", 1)),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("t", "v")
    assert case.searches[0].regressions[0].required_before == (("q", 1), ("s", 2))
    assert case.counts == TokenCounts(0, 0, 6, 6)
    check_evidence(model, case)


def test_silent_self_loop_preserves_its_enabling_requirement():
    model = net(
        ("p", "q", "f"),
        (("t", None), ("v", "A")),
        (("p", "t"), ("t", "p"), ("t", "q"), ("q", "v"), ("v", "f")),
        (("p", 1),),
        (("p", 1), ("f", 1)),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("t", "v")
    assert case.searches[0].regressions[0].required_before == (("p", 1),)
    check_evidence(model, case)


@pytest.mark.parametrize("final_only", [False, True])
def test_shortest_forward_lexical_path_relaxes_reverse_discovery_order(final_only):
    model = net(
        ("p", "x", "y", "q", "f"),
        (("a", None), ("b", None), ("c", None), ("z", None), ("v", "A")),
        (
            ("p", "a"),
            ("a", "x"),
            ("x", "z"),
            ("z", "q"),
            ("p", "b"),
            ("b", "y"),
            ("y", "c"),
            ("c", "q"),
            ("q", "v"),
            ("v", "f"),
        ),
        (("p", 1),),
        (("q" if final_only else "f", 1),),
    )
    case = replay_backwards(log("" if final_only else "A"), model).value.traces[0]
    assert ids(case) == (("a", "z") if final_only else ("a", "z", "v"))
    check_evidence(model, case)


def test_duplicate_activity_fires_exactly_one_and_can_plan_for_each_candidate():
    model = net(
        ("p", "q", "dead", "f"),
        (("a", "A"), ("b", "A"), ("tau", None)),
        (("dead", "a"), ("a", "f"), ("p", "tau"), ("tau", "q"), ("q", "b"), ("b", "f")),
        (("p", 1),),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("tau", "b")
    assert sum(step.kind == "visible" for step in case.steps) == 1
    check_evidence(model, case)
    direct = replace(model, initial_marking=Marking((("dead", 1), ("q", 1))))
    case = replay_backwards(log("A"), direct, BackwardsReplaySpec(1)).value.traces[0]
    assert ids(case) == ("a",)  # All direct candidates examined despite search cap 1.


def test_failed_cover_search_repairs_minimum_direct_deficit_then_id():
    model = net(
        ("p", "q", "f"),
        (("a", "A"), ("b", "A"), ("c", "A")),
        (
            ("p", "a", 3),
            ("a", "f"),
            ("q", "b", 2),
            ("b", "f"),
            ("q", "c", 2),
            ("c", "f"),
        ),
        (),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("b",)
    assert case.searches[0].exhausted
    assert case.steps[1].inserted_tokens == (("q", 2),)
    assert case.counts == TokenCounts(2, 0, 3, 1)
    check_evidence(model, case)


def test_exact_silent_completion_and_source_sink_transitions():
    model = net(
        ("p", "q", "f"),
        (("a", "A"), ("tau", None)),
        (("p", "a"), ("a", "q"), ("q", "tau"), ("tau", "f")),
        (("p", 1),),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model).value.traces[0]
    assert ids(case) == ("a", "tau")
    assert case.searches[-1].mode == "exact_final"
    check_evidence(model, case)
    source = net(("q",), (("make", None),), (("make", "q"),), (), (("q", 1),))
    sink = net(("q",), (("take", None),), (("q", "take"),), (("q", 1),), ())
    for model, transition in ((source, "make"), (sink, "take")):
        case = replay_backwards(log(""), model).value.traces[0]
        assert ids(case) == (transition,)
        assert case.final_reached is True
        assert case.counts == TokenCounts(0, 0, 1, 1)
        check_evidence(model, case)


def test_final_coverage_is_not_exact_completion():
    model = net(
        ("p",),
        (("grow", None),),
        (("p", "grow"), ("grow", "p", 2)),
        (("p", 3),),
        (("p", 2),),
    )
    case = replay_backwards(log(""), model).value.traces[0]
    assert case.final_reached is False
    assert case.counts == TokenCounts(0, 1, 2, 3)
    assert ids(case) == ()
    check_evidence(model, case)


def test_unknown_activity_and_final_deficit_are_explicit():
    model = sequence()
    case = replay_backwards(log("X"), model).value.traces[0]
    assert case.log_deviation_count == 1
    assert case.processed_event_count == 1
    assert case.steps[1].kind == "log_deviation"
    assert case.final_reached is False
    assert case.counts == TokenCounts(1, 1, 1, 1)
    assert case.steps[-1].inserted_tokens == (("f", 1),)
    check_evidence(model, case)


def test_backward_limit_never_repairs_an_unprocessed_event():
    model = net(
        ("p", "q", "f"),
        (("tau", None), ("v", "A")),
        (("p", "tau"), ("tau", "q"), ("q", "v"), ("v", "f")),
        (("p", 1),),
        (("f", 1),),
    )
    result = replay_backwards(log("A"), model, BackwardsReplaySpec(1))
    case = result.value.traces[0]
    assert result.status is ComputeStatus.PARTIAL
    assert case.status == "limited"
    assert case.final_reached is None
    assert case.processed_event_count == 0
    assert case.counts == TokenCounts(0, 1, 0, 1)
    assert all(step.kind != "finalize" for step in case.steps)
    assert result.value.completed_counts == TokenCounts()
    assert result.value.attempted_counts == case.counts
    check_evidence(model, case)
    complete = replay_backwards(log("A"), model, BackwardsReplaySpec(2))
    assert complete.status is ComputeStatus.COMPUTED
    assert complete.value.traces[0].counts == TokenCounts(0, 0, 3, 3)


def test_unbounded_exact_reverse_search_is_partial_with_processed_prefix():
    model = net(
        ("p",),
        (("consume", None), ("v", "A")),
        (("p", "consume", 2), ("consume", "p")),
        (),
        (("p", 1),),
    )
    result = replay_backwards(log("A"), model, BackwardsReplaySpec(5))
    case = result.value.traces[0]
    assert result.status is ComputeStatus.PARTIAL
    assert case.processed_event_count == 1
    assert case.final_reached is None
    assert case.searches[-1].admitted_states == 5
    assert case.searches[-1].limited
    assert case.counts == TokenCounts()
    check_evidence(model, case)


def test_cover_dominance_can_prove_failure_without_infinite_requirement_growth():
    model = net(
        ("p", "f"),
        (("consume", None), ("v", "A")),
        (("p", "consume", 2), ("consume", "p"), ("p", "v"), ("v", "f")),
        (),
        (("f", 1),),
    )
    case = replay_backwards(log("A"), model, BackwardsReplaySpec(1)).value.traces[0]
    assert case.status == "completed"
    assert case.searches[0].exhausted
    assert case.counts == TokenCounts(1, 0, 2, 1)
    check_evidence(model, case)


def test_distinct_visible_targets_also_obey_state_budget():
    model = net(
        ("p", "q", "f"),
        (("a", "A"), ("b", "A")),
        (("p", "a"), ("a", "f"), ("q", "b"), ("b", "f")),
        (),
        (("f", 1),),
    )
    result = replay_backwards(log("A"), model, BackwardsReplaySpec(1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces[0].searches[0].admitted_states == 1
    assert result.value.traces[0].processed_event_count == 0


def test_empty_population_and_empty_case():
    model = net((), (), (), (), ())
    empty = replay_backwards(log(), model)
    actual = replay_backwards(log(""), model)
    assert empty.status is ComputeStatus.COMPUTED
    assert empty.value.trace_count == 0
    assert empty.value.completed_counts == TokenCounts()
    assert actual.value.trace_count == 1
    assert actual.value.traces[0].final_reached is True
    assert actual.value.traces[0].counts == TokenCounts()


@pytest.mark.parametrize(
    "status",
    [ComputeStatus.PARTIAL, ComputeStatus.INVALID_INPUT, ComputeStatus.UNAVAILABLE],
)
def test_failed_upstream_result_preserves_identity_and_issues(status):
    source = case_traces(log("AB"))
    source = replace(
        source,
        status=status,
        value=source.value if status is ComputeStatus.PARTIAL else None,
        issues=(ComputeIssue("upstream", "Original failure"),),
    )
    result = replay_backwards(source, sequence())
    assert result.status is (
        ComputeStatus.INVALID_INPUT
        if status is ComputeStatus.INVALID_INPUT
        else ComputeStatus.UNAVAILABLE
    )
    assert result.value is None
    assert result.issues[0].code == "upstream"
    assert result.parent_computation_ids == (source.computation_id,)


def test_request_schema_identity_and_immutable_payload():
    source, model = case_traces(log("AB")), sequence()
    result = replay_backwards(source, model)
    again = replay_backwards(source, model)
    changed = replay_backwards(source, model, BackwardsReplaySpec(10))
    different_net = replay_backwards(source, replace(model, final_marking=Marking()))
    assert result == again
    assert len({item.computation_id for item in (result, changed, different_net)}) == 3
    assert result.spec.model_digest == model_digest(model)
    assert result.source_digest == source.source_digest
    assert RESULT_SCHEMAS[result.operator_id] == (
        "case_backwards_replay_set",
        BackwardsReplayRequest,
        BackwardsReplaySet,
    )
    with pytest.raises(FrozenInstanceError):
        result.value.trace_count = 3


@pytest.mark.parametrize(
    "limit,error",
    [(0, ValueError), (-1, ValueError), (True, TypeError), (1.0, TypeError)],
)
def test_invalid_limits(limit, error):
    with pytest.raises(error):
        BackwardsReplaySpec(limit)


def test_invalid_inputs():
    with pytest.raises(TypeError, match="net"):
        replay_backwards(log("A"), object())
    with pytest.raises(TypeError, match="spec"):
        replay_backwards(log("A"), sequence(), object())
    with pytest.raises(TypeError, match="CaseLog"):
        replay_backwards(object(), sequence())


def test_random_conservative_nets_against_independent_forward_search():
    rng = random.Random(91315)
    for _ in range(100):
        places = tuple(f"p{i}" for i in range(rng.randint(1, 3)))
        token_count = rng.randint(1, 3)

        def distributed(total):
            counts = {place: 0 for place in places}
            for _ in range(total):
                counts[rng.choice(places)] += 1
            return tuple((place, value) for place, value in counts.items() if value)

        transitions, arcs = [], []
        for i in range(rng.randint(0, 4)):
            transition_id = f"s{i}"
            transitions.append((transition_id, None))
            count = rng.randint(1, token_count)
            arcs.extend(
                (place, transition_id, value) for place, value in distributed(count)
            )
            arcs.extend(
                (transition_id, place, value) for place, value in distributed(count)
            )
        for i in range(rng.randint(1, 3)):
            transition_id = f"v{i}"
            transitions.append((transition_id, "A"))
            count = rng.randint(1, token_count)
            arcs.extend(
                (place, transition_id, value) for place, value in distributed(count)
            )
            arcs.extend(
                (transition_id, place, value) for place, value in distributed(count)
            )
        model = net(
            places,
            transitions,
            arcs,
            distributed(token_count),
            distributed(token_count),
        )
        result = replay_backwards(log("A"), model, BackwardsReplaySpec(10000))
        assert result.status is ComputeStatus.COMPUTED
        case = result.value.traces[0]
        enabling = forward_oracle(model, dict(model.initial_marking.tokens), "A")
        if enabling is None:
            assert case.searches[0].exhausted
            assert not case.searches[0].regressions
            current = dict(model.initial_marking.tokens)
            targets = tuple(t.id for t in model.transitions if t.activity == "A")
            target = min(
                targets,
                key=lambda candidate: (
                    sum(
                        max(amount - current.get(place, 0), 0)
                        for place, amount in incidence(model, candidate)[0].items()
                    ),
                    candidate,
                ),
            )
            for place, amount in incidence(model, target)[0].items():
                current[place] = max(current.get(place, 0), amount)
            after_visible = direct_fire(model, current, target)
            expected_visible_path = (target,)
        else:
            path, target, current = enabling
            expected_visible_path = path + (target,)
            after_visible = direct_fire(model, current, target)
            assert case.steps[len(path) + 1].inserted_tokens == ()
        completion = forward_oracle(model, after_visible)
        expected_path = expected_visible_path + (completion[0] if completion else ())
        assert ids(case) == expected_path
        assert case.final_reached is (completion is not None)
        check_evidence(model, case)
