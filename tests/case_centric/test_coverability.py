"""Independent finite-state oracles and executable pumping certificates."""

import random
from collections import deque
from dataclasses import FrozenInstanceError, dataclass, replace
from itertools import product

import pytest

from pix.case_centric.coverability import (
    CoverabilityAcceleration,
    CoverabilityBoundary,
    CoverabilityNode,
    CoverabilitySpec,
    OmegaMarking,
    PlaceBound,
    PumpingWitness,
    coverability,
)
from pix.compute.model_semantics import fire, model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus
from pix.results import result_from_json, result_json_bytes


def net(places, transitions, arcs, initial=(), final=()):
    return PetriNet(
        tuple(Place(p) for p in places),
        tuple(Transition(t, "same visible label") for t in transitions),
        tuple(Arc(*a) for a in arcs),
        Marking(tuple(initial)),
        Marking(tuple(final)),
    )


def oracle(model):
    """Exact BFS using direct arc arithmetic, independent of PIX firing/KM."""
    places = tuple(p.id for p in model.places)
    before = {
        t.id: tuple(
            sum(a.weight for a in model.arcs if a.source == p and a.target == t.id)
            for p in places
        )
        for t in model.transitions
    }
    after = {
        t.id: tuple(
            sum(a.weight for a in model.arcs if a.source == t.id and a.target == p)
            for p in places
        )
        for t in model.transitions
    }
    initial = tuple(dict(model.initial_marking.tokens).get(p, 0) for p in places)
    pending, states, enabled = deque((initial,)), {initial}, set()
    while pending:
        state = pending.popleft()
        for tid, consumed in before.items():
            if any(x < y for x, y in zip(state, consumed)):
                continue
            enabled.add(tid)
            target = tuple(x - y + z for x, y, z in zip(state, consumed, after[tid]))
            if target not in states:
                states.add(target)
                pending.append(target)
        assert len(states) <= 1000, (
            "oracle fixtures must have finite small reachability"
        )
    return states, enabled


def vectors(report):
    return {
        tuple(dict(n.marking.tokens).get(p, 0) for p in report.place_ids)
        for n in report.nodes
    }


def producer():
    return net(("p",), ("grow",), (("p", "grow"), ("grow", "p", 2)), (("p", 1),))


def test_producer_unboundedness_has_replayable_pumping_certificate():
    model = producer()
    result = coverability(model, CoverabilitySpec(target=Marking((("p", 10**30),))))
    report = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert result.source_digest == model_digest(model)
    assert report.complete and report.bounded is False
    assert report.target_coverable is True and report.target_covering_node_id == 1
    assert report.place_bounds == (PlaceBound("p", False, None, 1, 1),)
    assert report.nodes[1].marking == OmegaMarking((("p", None),))
    assert report.nodes[2].duplicate_ancestor_id == 1
    assert report.dead_transition_ids == ()
    witness = report.pumping_witnesses[0]
    assert witness.prefix_transition_ids == ()
    assert witness.cycle_transition_ids == ("grow",)
    assert witness.before == Marking((("p", 1),))
    assert witness.after == Marking((("p", 2),))
    current = model.initial_marking
    for transition in witness.prefix_transition_ids:
        current = fire(model, current, transition)
    assert current == witness.before
    for repeat in range(1, 101):
        for transition in witness.cycle_transition_ids:
            current = fire(model, current, transition)
        assert dict(current.tokens)["p"] == repeat + 1


def test_concrete_prefix_and_two_step_cycle_certificate():
    model = net(
        ("start", "p", "q"),
        ("begin", "split", "return"),
        (
            ("start", "begin"),
            ("begin", "p"),
            ("p", "split"),
            ("split", "q", 2),
            ("q", "return"),
            ("return", "p"),
        ),
        (("start", 1),),
    )
    report = coverability(model).value
    assert report.bounded is False
    witness = report.pumping_witnesses[0]
    state = model.initial_marking
    for tid in witness.prefix_transition_ids:
        state = fire(model, state, tid)
    assert state == witness.before
    for tid in witness.cycle_transition_ids:
        state = fire(model, state, tid)
    assert state == witness.after
    assert witness.prefix_transition_ids == ("begin",)
    assert witness.cycle_transition_ids == ("split", "return")
    for _ in range(20):
        for tid in witness.cycle_transition_ids:
            state = fire(model, state, tid)
    assert dict(state.tokens)["q"] > dict(witness.after.tokens)["q"]


def test_deadlock_is_bounded_and_dead_transition_is_proven():
    model = net(
        ("p", "q"),
        ("blocked",),
        (("p", "blocked", 2), ("blocked", "q", 3)),
        (("p", 1),),
    )
    result = coverability(model, CoverabilitySpec(target=Marking((("q", 1),))))
    assert result.value.bounded is True
    assert result.value.complete and len(result.value.nodes) == 1
    assert result.value.dead_transition_ids == ("blocked",)
    assert result.value.target_coverable is False
    assert tuple(p.bound for p in result.value.place_bounds) == (1, 0)
    assert not result.value.accelerations


def test_weighted_conservation_and_token_transfer_match_finite_oracle():
    # 2*p + q = 4; total unweighted token count is allowed to change.
    model = net(
        ("p", "q"),
        ("split", "join"),
        (("p", "split"), ("split", "q", 2), ("q", "join", 2), ("join", "p")),
        (("p", 2),),
    )
    report = coverability(model).value
    states, enabled = oracle(model)
    assert states == {(2, 0), (1, 2), (0, 4)}
    assert vectors(report) == states
    assert report.complete and report.bounded is True
    assert report.dead_transition_ids == () and enabled == {"split", "join"}
    assert tuple(b.bound for b in report.place_bounds) == (2, 4)
    assert all(2 * p + q == 4 for p, q in vectors(report))
    assert not report.accelerations


def test_swap_loop_is_bounded_but_does_not_claim_termination():
    model = net(
        ("p", "q"),
        ("left", "right"),
        (("p", "right"), ("right", "q"), ("q", "left"), ("left", "p")),
        (("p", 1),),
    )
    report = coverability(model).value
    assert report.bounded is True and vectors(report) == {(1, 0), (0, 1)}
    assert report.nodes[-1].duplicate_ancestor_id == 0
    assert not hasattr(report, "live") and not hasattr(report, "sound")
    assert not hasattr(report, "terminates")


def test_nested_omega_acceleration_preserves_symbolic_vs_concrete_witness():
    model = net(
        ("p", "q"),
        ("grow", "transfer"),
        (("p", "grow"), ("grow", "p", 2), ("p", "transfer"), ("transfer", "q")),
        (("p", 1),),
    )
    report = coverability(
        model, CoverabilitySpec(target=Marking((("p", 100), ("q", 100))))
    ).value
    assert report.complete and report.target_coverable is True
    assert OmegaMarking((("p", None), ("q", None))) in tuple(
        n.marking for n in report.nodes
    )
    q_certificate = next(
        a for a in report.accelerations if "q" in a.accelerated_place_ids
    )
    assert dict(q_certificate.successor.tokens)["p"] is None
    assert all("q" not in w.growing_place_ids for w in report.pumping_witnesses)
    assert all(b.bounded is False for b in report.place_bounds)


@pytest.mark.parametrize(
    "spec", (CoverabilitySpec(max_nodes=1), CoverabilitySpec(max_expansions=1))
)
def test_capped_finite_exploration_is_unknown_not_a_boundedness_proof(spec):
    model = net(
        ("p", "q", "r"),
        ("a", "b"),
        (("p", "a"), ("a", "q"), ("q", "b"), ("b", "r")),
        (("p", 1),),
    )
    result = coverability(model, replace(spec, target=Marking((("r", 1),))))
    assert result.status is ComputeStatus.PARTIAL
    assert not result.value.complete and result.value.bounded is None
    assert result.value.frontier_node_ids and result.value.boundary
    assert result.value.target_coverable is None
    assert result.value.dead_transition_ids == ()
    assert all(b.bounded is None and b.bound is None for b in result.value.place_bounds)
    assert tuple(i.code for i in result.issues) == (result.value.boundary[0].reason,)


def test_cap_after_acceleration_keeps_unboundedness_and_positive_cover_proof():
    result = coverability(
        producer(), CoverabilitySpec(max_nodes=2, target=Marking((("p", 999),)))
    )
    assert result.status is ComputeStatus.PARTIAL and not result.value.complete
    assert result.value.bounded is False and result.value.target_coverable is True
    assert result.value.pumping_witnesses
    assert result.value.dead_transition_ids == ()


def test_cap_exactly_at_completion_is_not_a_false_partial_result():
    empty = net((), (), ())
    result = coverability(empty, CoverabilitySpec(1, 1, Marking()))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.complete and result.value.bounded is True
    assert result.value.target_coverable is True
    assert result.value.nodes[0].expanded
    # Root plus one ancestor-duplicate leaf; only root is expanded.
    loop = net(("p",), ("loop",), (("p", "loop"), ("loop", "p")), (("p", 1),))
    result = coverability(loop, CoverabilitySpec(2, 1))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.expanded_nodes == 1


def test_coverability_is_not_exact_reachability_and_ignores_accepting_target():
    model = net(("p",), ("two",), (("two", "p", 2),), (), (("p", 1),))
    report = coverability(model, CoverabilitySpec(target=Marking((("p", 1),)))).value
    assert report.target_coverable is True and report.bounded is False
    # Odd token counts are unreachable; the query permits extra tokens.
    assert report.pumping_witnesses[0].after == Marking((("p", 2),))
    assert coverability(model).value.target_coverable is None


@pytest.mark.parametrize("initial,consume,produce", tuple(product(range(4), repeat=3)))
def test_all_small_one_place_nets_against_closed_form(initial, consume, produce):
    arcs = (("p", "t", consume),) if consume else ()
    arcs += (("t", "p", produce),) if produce else ()
    model = net(("p",), ("t",), arcs, (("p", initial),) if initial else ())
    report = coverability(model).value
    unbounded = initial >= consume and produce > consume
    assert report.complete and report.bounded is not unbounded
    assert bool(report.pumping_witnesses) is unbounded
    assert report.dead_transition_ids == (("t",) if initial < consume else ())
    if not unbounded:
        states, _ = oracle(model)
        assert vectors(report) == states
        assert report.place_bounds[0].bound == initial


def test_random_weighted_conservative_nets_against_independent_oracle():
    rng = random.Random(940271)
    places = ("p", "q", "r")
    for _ in range(30):
        arcs = []
        for tid in ("a", "b", "c"):
            # Total-token invariant bounds each net; pre/post may be weighted.
            count = rng.randint(1, 3)
            consumed = [rng.choice(places) for _ in range(count)]
            produced = [rng.choice(places) for _ in range(count)]
            for p in places:
                if consumed.count(p):
                    arcs.append((p, tid, consumed.count(p)))
                if produced.count(p):
                    arcs.append((tid, p, produced.count(p)))
        model = net(places, ("a", "b", "c"), arcs, (("p", 2), ("q", 1)))
        states, enabled = oracle(model)
        report = coverability(model).value
        assert report.complete and report.bounded is True
        assert vectors(report) == states
        assert set(report.dead_transition_ids) == {"a", "b", "c"} - enabled
        assert tuple(b.bound for b in report.place_bounds) == tuple(
            max(m[i] for m in states) for i in range(3)
        )


def test_branch_local_comparison_never_accelerates_unrelated_states():
    # Two alternative bounded outcomes (1,0) and (2,0); neither is the other's
    # ancestor. Global dominance would incorrectly infer unboundedness here.
    model = net(
        ("choice", "p"),
        ("one", "two"),
        (("choice", "one"), ("one", "p"), ("choice", "two"), ("two", "p", 2)),
        (("choice", 1),),
    )
    report = coverability(model).value
    assert report.bounded is True and not report.accelerations
    assert report.place_bounds[1].bound == 2


def test_transition_ids_not_labels_and_input_permutations_are_deterministic():
    model = net(
        ("p", "q"),
        ("a", "b"),
        (("p", "a"), ("a", "q"), ("p", "b"), ("b", "q")),
        (("p", 1),),
    )
    reordered = PetriNet(
        tuple(reversed(model.places)),
        tuple(reversed(model.transitions)),
        tuple(reversed(model.arcs)),
        model.initial_marking,
        model.final_marking,
    )
    first, second = coverability(model), coverability(reordered)
    assert first == second
    assert {node.transition_id for node in first.value.nodes[1:]} == {"a", "b"}
    assert (
        coverability(model, CoverabilitySpec(max_nodes=99)).computation_id
        != first.computation_id
    )
    assert (
        coverability(model, CoverabilitySpec(target=Marking())).computation_id
        != first.computation_id
    )
    with pytest.raises(FrozenInstanceError):
        first.value.bounded = False


@pytest.mark.parametrize("arc_type", ("reset", "inhibitor"))
def test_extended_arc_semantics_are_refused(arc_type):
    @dataclass(frozen=True)
    class ExtendedArc(Arc):
        kind: str = arc_type

    model = PetriNet(
        (Place("p"),),
        (Transition("t"),),
        (ExtendedArc("p", "t"),),
        Marking((("p", 1),)),
        Marking(),
    )
    with pytest.raises(TypeError, match="reset, inhibitor"):
        coverability(model)


def test_extended_net_semantics_and_invalid_requests_are_refused():
    class InhibitorNet(PetriNet):
        pass

    model = InhibitorNet((), (), (), Marking(), Marking())
    with pytest.raises(TypeError, match="standard weighted"):
        coverability(model)
    with pytest.raises(TypeError):
        coverability({})
    with pytest.raises(TypeError):
        coverability(producer(), {})
    with pytest.raises(ValueError, match="unknown place"):
        coverability(producer(), CoverabilitySpec(target=Marking((("unknown", 1),))))


@pytest.mark.parametrize("value", (0, -1, True, 1.5, "4"))
@pytest.mark.parametrize("field", ("max_nodes", "max_expansions"))
def test_spec_caps_are_strict_positive_integers(field, value):
    with pytest.raises((ValueError, TypeError)):
        CoverabilitySpec(**{field: value})


@pytest.mark.parametrize(
    "tokens",
    (
        [("p", 1)],
        (("p", 0),),
        (("p", -1),),
        (("p", True),),
        (("p", float("inf")),),
        (("p", 1), ("p", None)),
        (("", 1),),
        (("p",),),
    ),
)
def test_omega_markings_validate_immutable_finite_or_explicit_omega(tokens):
    with pytest.raises((TypeError, ValueError)):
        OmegaMarking(tokens)


def test_nested_payload_validation_rejects_contradictory_claims():
    with pytest.raises(TypeError):
        CoverabilitySpec(target=OmegaMarking())
    with pytest.raises(ValueError):
        CoverabilityNode(1, 1, "t", OmegaMarking(), ())
    with pytest.raises(ValueError):
        CoverabilityAcceleration(1, 0, OmegaMarking(), (), ("t",))
    with pytest.raises(ValueError):
        PumpingWitness(
            0, 1, (), ("t",), Marking((("p", 2),)), Marking((("p", 1),)), ("p",)
        )
    with pytest.raises(ValueError):
        PlaceBound("p", True, None, 1, None)
    with pytest.raises(ValueError):
        CoverabilityBoundary(0, "t", "token_threshold")
    partial = coverability(producer(), CoverabilitySpec(max_nodes=1)).value
    with pytest.raises(ValueError, match="complete tree"):
        replace(partial, bounded=True)
    with pytest.raises(ValueError, match="pumping witness"):
        replace(partial, bounded=False)
    with pytest.raises(ValueError, match="completion"):
        replace(partial, target=Marking(), target_coverable=False)


def test_report_rejects_forged_global_proof_claims_and_noncovering_node():
    report = coverability(
        producer(), CoverabilitySpec(target=Marking((("p", 99),)))
    ).value
    with pytest.raises(ValueError, match="omega evidence"):
        replace(report, bounded=True)
    with pytest.raises(ValueError, match="does not cover"):
        replace(report, target_covering_node_id=0)
    with pytest.raises(ValueError, match="dead transitions"):
        replace(report, dead_transition_ids=("does_not_exist",))
    with pytest.raises(ValueError, match="frontier"):
        replace(
            report,
            expanded_nodes=0,
            nodes=tuple(replace(n, expanded=False) for n in report.nodes),
        )


def test_report_rejects_missing_acceleration_and_false_closed_branch():
    report = coverability(producer()).value
    with pytest.raises(ValueError, match="omega changes"):
        replace(report, accelerations=(), pumping_witnesses=report.pumping_witnesses)
    with pytest.raises(ValueError, match="same marking"):
        replace(
            report,
            nodes=report.nodes[:2]
            + (replace(report.nodes[2], duplicate_ancestor_id=0),),
        )


@pytest.mark.parametrize(
    "spec",
    (
        CoverabilitySpec(),
        CoverabilitySpec(max_nodes=1),
        CoverabilitySpec(max_nodes=2, target=Marking((("p", 10**30),))),
    ),
)
def test_registered_results_roundtrip_omega_witnesses_and_unknown(spec):
    result = coverability(producer(), spec)
    assert result_from_json(result_json_bytes(result)) == result
