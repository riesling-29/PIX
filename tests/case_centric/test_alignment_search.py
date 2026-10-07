"""Certified bounds and search checked against independent finite graph oracles."""

from dataclasses import replace
from fractions import Fraction
from itertools import product
from types import SimpleNamespace

import pytest

from pix.case_centric import alignment_search as search
from pix.case_centric.alignment_search import (
    DiscountedAStarSpec,
    StateEquationAStarSpec,
    align_discounted_astar,
    align_state_equation_astar,
)
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}_{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def state_net(edges, start="s", end="f"):
    nodes = (
        {start, end}
        | {source for source, _, _ in edges}
        | {target for _, target, _ in edges}
    )
    return PetriNet(
        tuple(Place(node) for node in sorted(nodes)),
        tuple(Transition(f"t{i}", label) for i, (_, _, label) in enumerate(edges)),
        tuple(
            arc
            for i, (source, target, _) in enumerate(edges)
            for arc in (
                Arc(source, f"t{i}"),
                Arc(f"t{i}", target),
            )
        ),
        Marking(((start, 1),)),
        Marking(((end, 1),)),
    )


def graph_oracle(edges, word, costs, start="s", end="f"):
    # Direct graph semantics; independent of PIX enabled/fire/search methods.
    nodes = (
        {start, end}
        | {source for source, _, _ in edges}
        | {target for _, target, _ in edges}
    )
    states = tuple(product(range(len(word) + 1), sorted(nodes)))
    arcs = []
    for position, node in states:
        if position < len(word):
            arcs.append(((position, node), (position + 1, node), costs.log_move_cost))
        for source, target, label in edges:
            if source != node:
                continue
            arcs.append(
                (
                    (position, node),
                    (position, target),
                    costs.silent_move_cost if label is None else costs.model_move_cost,
                )
            )
            if label is not None and position < len(word) and word[position] == label:
                arcs.append(
                    (
                        (position, node),
                        (position + 1, target),
                        costs.synchronous_move_cost,
                    )
                )
    distance = {(0, start): 0}
    for _ in range(len(states) - 1):
        changed = False
        for source, target, cost in arcs:
            if source in distance and (
                target not in distance or distance[source] + cost < distance[target]
            ):
                distance[target] = distance[source] + cost
                changed = True
        if not changed:
            break
    return distance.get((len(word), end))


def discounted_graph_oracle(edges, word, costs, horizon, gamma, start="s", end="f"):
    # Layered dynamic programming is acyclic by move index, unlike the A* heap.
    layer = {(0, start): Fraction()}
    best_goal = Fraction() if not word and start == end else None
    for depth in range(horizon):
        following = {}
        for (position, node), cost in layer.items():
            options = []
            if position < len(word):
                options.append(((position + 1, node), costs.log_move_cost))
            for source, target, label in edges:
                if source == node:
                    options.append(
                        (
                            (position, target),
                            costs.silent_move_cost
                            if label is None
                            else costs.model_move_cost,
                        )
                    )
                    if (
                        label is not None
                        and position < len(word)
                        and word[position] == label
                    ):
                        options.append(
                            ((position + 1, target), costs.synchronous_move_cost)
                        )
            for state, base in options:
                candidate = cost + base * gamma**depth
                if state not in following or candidate < following[state]:
                    following[state] = candidate
        layer = following
        candidate = layer.get((len(word), end))
        if candidate is not None and (best_goal is None or candidate < best_goal):
            best_goal = candidate
    return best_goal


def assert_witness(trace, net, observed):
    # Independent weighted-token accounting of the emitted path.
    marking = dict(net.initial_marking.tokens)
    consumed = []
    for index, move in enumerate(trace.moves):
        assert tuple(sorted(marking.items())) == move.before_marking
        if move.transition_id is not None:
            inputs = {
                arc.source: arc.weight
                for arc in net.arcs
                if arc.target == move.transition_id
            }
            outputs = {
                arc.target: arc.weight
                for arc in net.arcs
                if arc.source == move.transition_id
            }
            assert all(
                marking.get(place, 0) >= weight for place, weight in inputs.items()
            )
            for place, weight in inputs.items():
                marking[place] -= weight
            for place, weight in outputs.items():
                marking[place] = marking.get(place, 0) + weight
            marking = {place: count for place, count in marking.items() if count}
        if move.event_id is not None:
            consumed.append(move.activity)
        assert tuple(sorted(marking.items())) == move.after_marking
        assert Fraction(*trace.step_costs[index]) >= 0
    assert tuple(consumed) == tuple(observed)
    assert tuple(sorted(marking.items())) == net.final_marking.tokens
    assert sum((Fraction(*cost) for cost in trace.step_costs), Fraction()) == Fraction(
        *trace.cost
    )


@pytest.mark.parametrize(
    "edges",
    (
        (("s", "f", "A"),),
        (("s", "m", "A"), ("m", "f", "B")),
        (("s", "m", None), ("m", "s", None), ("m", "f", "A")),
        (("s", "l", "A"), ("s", "r", "A"), ("l", "f", "B"), ("r", "f", "A")),
        (("s", "dead", "A"),),
    ),
)
@pytest.mark.parametrize(
    "costs",
    (
        AlignmentSpec(),
        AlignmentSpec(log_move_cost=2, model_move_cost=3, silent_move_cost=1),
        AlignmentSpec(log_move_cost=0, model_move_cost=0, synchronous_move_cost=2),
    ),
)
@pytest.mark.parametrize("backend", ("exact_simplex", "exact_vertices"))
def test_exact_state_equation_astar_matches_independent_bellman_ford(
    edges, costs, backend
):
    words = tuple(
        word for length in range(3) for word in product(("A", "B"), repeat=length)
    )
    net = state_net(edges)
    result = align_state_equation_astar(
        log(*words), net, StateEquationAStarSpec(alignment=costs, backend=backend)
    )
    assert result.status is ComputeStatus.COMPUTED
    for word, trace in zip(words, result.value.traces):
        expected = graph_oracle(edges, word, costs)
        assert (None if trace.cost is None else Fraction(*trace.cost)) == expected
        if expected is not None:
            assert trace.status == "optimal"
            assert_witness(trace, net, word)
        else:
            assert trace.status == "unreachable"


def test_heuristic_is_a_nonzero_actual_lp_bound_and_preserves_rational_relaxation():
    # One weighted A firing produces two final-place tokens. Target only one:
    # the LP needs half a firing, while no executable final marking exists.
    net = PetriNet(
        (Place("s"), Place("f")),
        (Transition("a", "A"),),
        (Arc("s", "a", 2), Arc("a", "f", 2)),
        Marking((("s", 1),)),
        Marking((("f", 1),)),
    )
    value = align_state_equation_astar(log(""), net).value
    bound = value.traces[0].heuristic_evidence[0]
    assert bound.certificate_status == "exact_optimum"
    assert bound.exact_objective == (1, 2)
    assert bound.integer_lower_bound == 1
    assert value.traces[0].status == "unreachable"


def test_concurrent_weighted_net_alignment_executes_exact_weighted_arcs():
    net = PetriNet(
        tuple(Place(p) for p in ("s", "pa", "pb", "c", "d", "f")),
        (
            Transition("split"),
            Transition("ta", "A"),
            Transition("tb", "B"),
            Transition("join"),
        ),
        (
            Arc("s", "split"),
            Arc("split", "pa", 2),
            Arc("split", "pb"),
            Arc("pa", "ta", 2),
            Arc("ta", "c"),
            Arc("pb", "tb"),
            Arc("tb", "d"),
            Arc("c", "join"),
            Arc("d", "join"),
            Arc("join", "f"),
        ),
        Marking((("s", 1),)),
        Marking((("f", 1),)),
    )
    words = ("AB", "BA", "A", "BBA")
    value = align_state_equation_astar(log(*words), net).value
    assert [trace.cost for trace in value.traces] == [(0, 1), (0, 1), (1, 1), (1, 1)]
    for word, trace in zip(words, value.traces):
        assert_witness(trace, net, word)


@pytest.mark.parametrize("gamma", ((1, 1), (1, 2), (2, 3)))
@pytest.mark.parametrize("horizon", (1, 2, 4))
@pytest.mark.parametrize("backend", ("exact_simplex", "exact_vertices"))
def test_discounted_astar_matches_independent_layered_graph_oracle(
    gamma, horizon, backend
):
    edges = (("s", "s", None), ("s", "m", "A"), ("m", "f", "B"), ("s", "f", "B"))
    net = state_net(edges)
    costs = AlignmentSpec()
    words = ((), ("A",), ("B",), ("B", "A"))
    result = align_discounted_astar(
        log(*words),
        net,
        DiscountedAStarSpec(horizon, gamma, StateEquationAStarSpec(backend=backend)),
    )
    assert result.status is ComputeStatus.COMPUTED
    for word, trace in zip(words, result.value.traces):
        expected = discounted_graph_oracle(
            edges, word, costs, horizon, Fraction(*gamma)
        )
        assert (None if trace.cost is None else Fraction(*trace.cost)) == expected
        assert trace.status == (
            "optimal_within_horizon"
            if expected is not None
            else "unreachable_within_horizon"
        )
        if expected is not None:
            assert_witness(trace, net, word)


def test_discounted_depth_cannot_be_merged_with_same_marking():
    net = state_net((("s", "s", None), ("s", "f", "A")))
    trace = align_discounted_astar(log(""), net, DiscountedAStarSpec(3)).value.traces[0]
    assert trace.cost == (1, 4)
    assert tuple(move.kind for move in trace.moves) == ("silent", "silent", "model")
    assert trace.step_costs == ((0, 1), (0, 1), (1, 4))


@pytest.mark.parametrize(
    "limit",
    (
        {"backend": "exact_vertices", "max_bases": 1},
        {"max_lp_iterations": 1},
        {"max_lp_solves": 1},
        {"max_matrix_cells": 1},
    ),
)
def test_heuristic_limits_use_explicit_zero_bound_without_fabricating_nonfit(limit):
    net = state_net((("s", "m", "A"), ("m", "f", "B")))
    result = align_state_equation_astar(log("AB"), net, StateEquationAStarSpec(**limit))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.traces[0].cost == (0, 1)
    assert any(
        "zero_bound" in item.certificate_status
        for item in result.value.traces[0].heuristic_evidence
    )
    assert any(
        issue.code == "heuristic_conservative_zero_bound" for issue in result.issues
    )
    assert_witness(result.value.traces[0], net, "AB")


def test_default_simplex_retains_exact_dual_and_pivot_evidence():
    source = case_traces(log("X"))
    net = state_net((("s", "m", "A"), ("m", "f", "B")))
    spec = StateEquationAStarSpec()
    result = align_state_equation_astar(source, net, spec)
    assert result.value.backend == "exact_simplex"
    assert result.value.backend_version == "pix_exact_rational_simplex_v1"
    bound = result.value.traces[0].heuristic_evidence[0]
    assert bound.certificate_kind == "primal_dual_optimal"
    assert bound.lp_iterations > 0
    matrix, rhs, costs, row_names = search._state_equation(
        net, source.value.traces[0], 0, net.initial_marking, spec
    )
    assert bound.dual_rows == row_names
    dual = tuple(Fraction(*value) for value in bound.dual_values)
    assert all(
        sum(row[j] * y for row, y in zip(matrix, dual)) <= cost
        for j, cost in enumerate(costs)
    )
    assert (
        sum(value * y for value, y in zip(rhs, dual))
        == Fraction(*bound.exact_objective)
        == 3
    )


def test_simplex_infeasible_pruning_retains_original_row_farkas_certificate():
    source = case_traces(log("A"))
    net = state_net((("s", "dead", "A"),))
    spec = StateEquationAStarSpec()
    result = align_state_equation_astar(source, net, spec)
    trace = result.value.traces[0]
    assert trace.status == "unreachable"
    assert trace.expanded_states == 0
    bound = trace.heuristic_evidence[0]
    assert bound.infeasibility_proven
    assert bound.certificate_kind == "farkas_infeasible"
    assert bound.exact_objective is None
    matrix, rhs, costs, row_names = search._state_equation(
        net, source.value.traces[0], 0, net.initial_marking, spec
    )
    dual = tuple(Fraction(*value) for value in bound.dual_values)
    assert bound.dual_rows == row_names
    assert all(
        sum(row[j] * y for row, y in zip(matrix, dual)) <= 0 for j in range(len(costs))
    )
    assert sum(value * y for value, y in zip(rhs, dual)) > 0


@pytest.mark.parametrize("mode", ("uncertified", "invalid_farkas", "unknown_incumbent"))
def test_simplex_unusable_report_never_prunes_or_uses_incumbent_as_lower_bound(
    monkeypatch, mode
):
    def solver(costs, *, equalities, equality_rhs, **kwargs):
        return SimpleNamespace(
            status="unknown" if mode == "unknown_incumbent" else "infeasible",
            iterations=1,
            certificate_validated=mode != "uncertified",
            certificate_kind="feasible_incumbent"
            if mode == "unknown_incumbent"
            else "farkas_infeasible",
            dual_equalities=((0, 1),) * len(equality_rhs),
            objective=None,
            incumbent_cost=(1000, 1),
        )

    monkeypatch.setattr(search, "_backend", lambda spec: (solver, "test-double"))
    net = state_net((("s", "f", "A"),))
    result = align_state_equation_astar(log("A"), net)
    assert result.value.traces[0].cost == (0, 1)
    assert all(
        not bound.infeasibility_proven and bound.integer_lower_bound == 0
        for bound in result.value.traces[0].heuristic_evidence
    )
    assert_witness(result.value.traces[0], net, "A")


@pytest.mark.parametrize("limit", (0, -1, True, 1.5))
def test_simplex_iteration_budget_requires_positive_integer(limit):
    with pytest.raises(ValueError):
        StateEquationAStarSpec(max_lp_iterations=limit)


def test_simplex_workspace_budget_includes_artificial_and_certificate_matrices(
    monkeypatch,
):
    def should_not_run(*args, **kwargs):
        raise AssertionError("simplex should be excluded before workspace allocation")

    monkeypatch.setattr(
        search, "_backend", lambda spec: (should_not_run, "test-double")
    )
    net = state_net((("s", "f", "A"),))
    # Initial A*x=b has only 2*1=2 cells. Tableau + row-transform need 12.
    result = align_state_equation_astar(
        log(""), net, StateEquationAStarSpec(max_matrix_cells=10)
    )
    assert result.value.traces[0].cost == (1, 1)
    assert all(
        bound.certificate_status == "heuristic_matrix_limit_zero_bound"
        for bound in result.value.traces[0].heuristic_evidence
    )
    assert_witness(result.value.traces[0], net, "")


def test_search_limit_retains_admissible_lower_bound_and_unknown_optimum():
    net = state_net((("s", "f", "A"),))
    result = align_state_equation_astar(
        log(""), net, StateEquationAStarSpec(alignment=AlignmentSpec(max_states=1))
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces[0].status == "search_limit"
    assert result.value.traces[0].cost is None
    assert result.value.traces[0].lower_bound_cost == (1, 1)


def test_dual_validation_rejects_any_exact_inequality_violation():
    assert search._certify_dual(((1,),), (1,), (1,), (1.001,), 1000000) is None
    certificate = search._certify_dual(((2,),), (1,), (1,), (0.5,), 1000000)
    assert certificate == (Fraction(1, 2), (Fraction(1, 2),))
    # Nearly integral numerical dual reconstructs exactly, then is checked.
    assert search._certify_dual(((1,),), (1,), (1,), (1.00000000001,), 1000000)[0] == 1


def test_optional_solver_is_unavailable_on_loader_failure_without_fallback(monkeypatch):
    def unavailable(spec):
        raise ImportError("native backend unavailable")

    monkeypatch.setattr(search, "_backend", unavailable)
    result = align_state_equation_astar(
        log("A"),
        state_net((("s", "f", "A"),)),
        StateEquationAStarSpec(backend="scipy_highs"),
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[-1].code == "lp_backend_unavailable"


def test_lazy_native_solver_loader_failure_is_also_unavailable(monkeypatch):
    def solver(*args, **kwargs):
        raise OSError("test native loader failure")

    monkeypatch.setattr(search, "_backend", lambda spec: (solver, "test-double"))
    result = align_state_equation_astar(
        log("A"),
        state_net((("s", "f", "A"),)),
        StateEquationAStarSpec(backend="scipy_highs"),
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_discounted_zero_horizon_only_accepts_initial_final_empty_case():
    accepted = align_discounted_astar(
        log("", "A"), state_net((), "s", "s"), DiscountedAStarSpec(0)
    )
    assert accepted.value.traces[0].status == "optimal_within_horizon"
    assert accepted.value.traces[0].cost == (0, 1)
    assert accepted.value.traces[1].status == "unreachable_within_horizon"


@pytest.mark.parametrize("mode", ("infeasible", "bad_dual", "exception"))
def test_unverified_numeric_solver_results_never_prune_reachable_behavior(
    monkeypatch, mode
):
    def solver(costs, *, A_eq, b_eq, **kwargs):
        if mode == "exception":
            raise ValueError("numeric issue")
        if mode == "infeasible":
            return SimpleNamespace(success=False, status=2)
        return SimpleNamespace(
            success=True, status=0, eqlin=SimpleNamespace(marginals=[10.25] * len(b_eq))
        )

    monkeypatch.setattr(
        search, "_backend", lambda spec: (solver, "test-double-not-scipy-validation")
    )
    result = align_state_equation_astar(
        log("A"),
        state_net((("s", "f", "A"),)),
        StateEquationAStarSpec(backend="scipy_highs"),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.traces[0].cost == (0, 1)
    assert any(
        "zero_bound" in item.certificate_status
        for item in result.value.traces[0].heuristic_evidence
    )


def test_model_identity_empty_cases_and_invalid_input_status():
    source = case_traces(log(""))
    accepted = state_net((), "s", "s")
    result = align_state_equation_astar(source, accepted)
    assert result.value.traces[0].cost == (0, 1)
    assert result.spec.model_digest == result.value.model_digest
    assert result.parent_computation_ids == (source.computation_id,)
    assert align_state_equation_astar(log(), accepted).value.requested_count == 0
    failed = replace(source, status=ComputeStatus.INVALID_INPUT, value=None)
    assert (
        align_state_equation_astar(failed, accepted).status
        is ComputeStatus.INVALID_INPUT
    )


@pytest.mark.parametrize("discount", ((0, 1), (2, 1), (1, 0), (True, 2), (1.0, 2)))
def test_invalid_discount_is_rejected(discount):
    with pytest.raises((TypeError, ValueError)):
        DiscountedAStarSpec(2, discount)


@pytest.mark.parametrize("discounted", (False, True))
def test_search_result_round_trip_registered_schema(monkeypatch, discounted):
    import pix.results as persistence

    original = persistence._schemas
    monkeypatch.setattr(
        persistence, "_schemas", lambda: {**original(), **search.RESULT_SCHEMAS}
    )
    net = state_net((("s", "s", None), ("s", "f", "A")))
    result = (
        align_discounted_astar(log(""), net, DiscountedAStarSpec(3))
        if discounted
        else align_state_equation_astar(log("A", "B"), net)
    )
    assert persistence.result_from_json(persistence.result_json_bytes(result)) == result
