from collections import deque
from itertools import combinations, product

import pytest

from pix.case_centric.extended_discovery import RegionDiscoverySpec, discover_regions
from pix.contracts.models import Marking
from pix.contracts.result import ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(
                        f"e{i}_{j}",
                        (CaseAttribute("concept:name", "string", a),),
                    )
                    for j, a in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def accepts(net, word):
    """Independent multiset firing oracle, including arbitrary silent closure."""
    states = deque([(net.initial_marking.tokens, 0)])
    seen = set(states)
    while states:
        marking, index = states.popleft()
        if index == len(word) and marking == net.final_marking.tokens:
            return True
        for transition in net.transitions:
            if transition.activity is not None and (
                index == len(word) or transition.activity != word[index]
            ):
                continue
            tokens = dict(marking)
            incoming = [a for a in net.arcs if a.target == transition.id]
            if any(tokens.get(a.source, 0) < a.weight for a in incoming):
                continue
            for arc in incoming:
                tokens[arc.source] -= arc.weight
            for arc in net.arcs:
                if arc.source == transition.id:
                    tokens[arc.target] = tokens.get(arc.target, 0) + arc.weight
            successor = (
                tuple(sorted((p, n) for p, n in tokens.items() if n)),
                index + (transition.activity is not None),
            )
            if successor not in seen:
                seen.add(successor)
                states.append(successor)
        assert len(seen) < 10000
    return False


def test_sequence_and_global_minimum_arc_weight():
    result = discover_regions(log(("A", "B")))
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    assert value.optimal_within_bounds and value.all_targets_separated
    assert (value.objective_arc_weight, value.objective_place_count) == (4, 2)
    for word in ((), ("A",), ("B",), ("B", "A"), ("A", "A", "B"), ("A", "B", "B")):
        assert not accepts(value.model, word)
    assert accepts(value.model, ("A", "B"))


@pytest.mark.parametrize(
    "words",
    [
        (("A", "B"), ("A", "C")),
        (("A", "B", "C"), ("A", "C", "B")),
        (("A",), ("A", "A")),
        ((), ("A",)),
        ((),),
        (("start", "end", "region_0"),),
    ],
)
def test_all_observed_traces_fit_and_exact_final_marking(words):
    result = discover_regions(log(*words))
    assert result.status in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL)
    for word in words:
        assert accepts(result.value.model, word)
    assert result.value.model.initial_marking == Marking((("source", 1),))
    assert result.value.model.final_marking == Marking((("sink", 1),))


def test_weighted_region_can_block_a_prefix_extension_binary_cannot():
    data = log(("A", "A", "B"))
    binary = discover_regions(data, RegionDiscoverySpec(max_arc_weight=1)).value
    weighted = discover_regions(data, RegionDiscoverySpec(max_arc_weight=2)).value

    def target(value):
        return next(
            x
            for x in value.separation_targets
            if x.prefix == ("A",) and x.next_activity == "B"
        )

    assert not target(binary).separated
    assert target(weighted).separated
    assert any(a.weight == 2 for a in weighted.model.arcs)
    assert weighted.optimal_within_bounds
    assert accepts(weighted.model, ("A", "A", "B"))
    assert not accepts(weighted.model, ("A", "B"))


def test_artificial_boundary_weights_use_observed_token_bound():
    value = discover_regions(log(("A", "A"))).value
    assert any(a.weight == 2 and a.source == "start" for a in value.model.arcs)
    assert all(
        a.weight == 1
        for a in value.model.arcs
        if a.source.startswith("activity_") or a.target.startswith("activity_")
    )


def test_variable_repetitions_expose_inseparable_language_limit():
    result = discover_regions(log(("A",), ("A", "A")))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.optimal_within_bounds
    assert any(
        x.prefix == () and x.next_activity is None and not x.separated
        for x in result.value.separation_targets
    )
    assert accepts(result.value.model, ())
    assert any(i.code == "inseparable_extensions" for i in result.issues)


def test_witness_region_equations_hold_for_every_observed_prefix():
    words = (("A", "B", "C"), ("A", "C", "B"))
    result = discover_regions(log(*words)).value
    for region in result.regions:
        assert region.arc_weight_cost == region.initial + region.final + sum(
            region.consume
        ) + sum(region.produce)
        for word in words:
            tokens = region.initial
            for activity in word:
                i = result.alphabet.index(activity)
                assert tokens >= region.consume[i]
                tokens += region.produce[i] - region.consume[i]
                assert 0 <= tokens <= 2
            assert tokens == region.final


def test_optimizer_matches_independent_exhaustive_subsets():
    """Enumerate binary assignments independently for AB, then every subset.

    The oracle calculates whole-trace accepted language through the equation;
    it does not call the production region enumerator or optimizer.
    """
    alphabet = ("A", "B")
    prefixes = ((), ("A",), ("A", "B"))
    targets = [(p, a) for p in prefixes for a in alphabet if p + (a,) not in prefixes]
    targets += [(p, None) for p in prefixes if p != ("A", "B")]
    feasible = []
    for initial, ca, cb, pa, pb in product(range(2), repeat=5):
        if initial < ca or initial - ca + pa < cb:
            continue
        markings = (initial, initial - ca + pa, initial - ca + pa - cb + pb)
        if min(markings) < 0 or max(markings) > 1:
            continue
        final = markings[-1]
        mask = frozenset(
            i
            for i, (prefix, a) in enumerate(targets)
            if (
                markings[len(prefix)] != final
                if a is None
                else markings[len(prefix)] < (ca if a == "A" else cb)
            )
        )
        if mask:
            feasible.append((mask, initial + ca + cb + pa + pb + final))
    goal = frozenset().union(*(m for m, _ in feasible))
    best = None
    for count in range(1, len(feasible) + 1):
        # Once count exceeds a proven arc-weight optimum it cannot improve it.
        if best and count > best[0]:
            break
        for selected in combinations(feasible, count):
            if frozenset().union(*(m for m, _ in selected)) == goal:
                objective = sum(w for _, w in selected), count
                best = min(best, objective) if best else objective
    actual = discover_regions(
        log(("A", "B")), RegionDiscoverySpec(max_observed_tokens=1)
    ).value
    assert best == (actual.objective_arc_weight, actual.objective_place_count)


@pytest.mark.parametrize(
    "spec",
    [
        RegionDiscoverySpec(max_assignments=1),
        RegionDiscoverySpec(max_region_checks=1),
        RegionDiscoverySpec(max_optimizer_states=1),
        RegionDiscoverySpec(max_optimizer_checks=1),
        RegionDiscoverySpec(max_prefixes=1),
    ],
)
def test_explicit_limits_never_publish_a_substitute_or_nonoptimal_model(spec):
    result = discover_regions(log(("A", "B")), spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any(issue.code == "region_limit" for issue in result.issues)


def test_frequency_ignored_but_source_provenance_changes():
    one = discover_regions(log(("A", "B")))
    repeated = discover_regions(log(("A", "B"), ("A", "B")))
    assert one.value == repeated.value
    assert one.computation_id != repeated.computation_id


@pytest.mark.parametrize("value", [True, 0, -1, 1.5])
def test_invalid_integer_bound(value):
    with pytest.raises(ValueError):
        RegionDiscoverySpec(max_arc_weight=value)


def test_empty_log_is_not_an_empty_case():
    assert discover_regions(log()).status is ComputeStatus.INVALID_INPUT
    result = discover_regions(log(()))
    assert result.status is ComputeStatus.COMPUTED
    assert accepts(result.value.model, ())


def test_codec_contract_triples_and_frozen_payload():
    from dataclasses import FrozenInstanceError

    from pix.case_centric.extended_discovery import RESULT_SCHEMAS
    from pix.results import _decode, _encode

    result = discover_regions(log(("A", "B")))
    kind, spec_type, payload_type = RESULT_SCHEMAS[result.operator_id]
    assert kind == "integer-region-discovery"
    assert _decode(_encode(result.spec), spec_type) == result.spec
    assert _decode(_encode(result.value), payload_type) == result.value
    with pytest.raises(FrozenInstanceError):
        result.value.optimal_within_bounds = False
