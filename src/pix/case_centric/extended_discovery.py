"""Native finite integer-region Petri-net discovery.

This is a bounded region-theory synthesis profile, not an alias for PM4Py's
causal-pair ILP miner. It solves two genuine integer problems without a solver
dependency: enumerate every feasible bounded integer place and then solve a
minimum-weight set cover exactly over separable observed-prefix extensions.
The region equation follows language-based region theory, e.g. van der Werf
et al., Process Discovery using Integer Linear Programming (2008/2009):
https://pure.tue.nl/ws/files/3092412/633716.pdf

PIX's explicit differences are a finite arc/observed-marking domain, a common
terminal marking, and global extension-cover objective. Exhaustion of either
enumeration or optimization limits returns unavailable with no substitute
model. A completed search is optimal only within those declared finite bounds.
Noise is not filtered: every observed trace is executable and accepting.
That property does not imply soundness, absence of extra behavior, or parity
with the upstream ILP formulation/solver/defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import product
from typing import ClassVar

from pix.case_centric._input import CaseInput, as_case_traces
from pix.case_centric.models_extended import (
    IntegerRegion,
    RegionDiscovery,
    SeparationTarget,
    _region_petri_net,
)
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class RegionDiscoverySpec:
    """Activity-to-region arc weights are integers in 0..max_arc_weight.

    Every observed prefix marking, including empty/full prefixes, must be in
    0..max_observed_tokens. Artificial start/end arcs carry the initial/final
    region token count and are bounded by max_observed_tokens independently
    of max_arc_weight; max_arc_weight=1 is not a unit-arc-net guarantee.
    ``max_assignments`` bounds the entire rectangular
    search domain before enumeration. ``max_region_checks`` separately bounds
    prefix enabling and negative-extension comparisons. The selected objective
    lexicographically minimizes total region arc weight and number of places;
    fixed source/phase/sink scaffolding is excluded from that objective.
    """

    SPEC_TYPE: ClassVar[str] = "pix.case_centric.RegionDiscoverySpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_arc_weight: int = 1
    max_observed_tokens: int = 2
    max_assignments: int = 1_000_000
    max_region_checks: int = 5_000_000
    max_optimizer_states: int = 100_000
    max_optimizer_checks: int = 5_000_000
    max_prefixes: int = 10_000

    def __post_init__(self) -> None:
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        for name in (
            "max_arc_weight",
            "max_observed_tokens",
            "max_assignments",
            "max_region_checks",
            "max_optimizer_states",
            "max_optimizer_checks",
            "max_prefixes",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


class _Limit(Exception):
    pass


def _finite_domain_size(spec: RegionDiscoverySpec, dimensions: int) -> int:
    """Stop multiplying when already out of budget (no enormous powers)."""
    size = spec.max_observed_tokens + 1
    for _ in range(dimensions):
        size *= spec.max_arc_weight + 1
        if size > spec.max_assignments:
            raise _Limit("Integer-region assignment domain exceeds max_assignments")
    if size > spec.max_assignments:
        raise _Limit("Integer-region assignment domain exceeds max_assignments")
    return size


def _enumerate_regions(words, alphabet, spec):
    n = len(alphabet)
    domain_size = _finite_domain_size(spec, 2 * n)
    prefixes = {()}
    for word in words:
        if len(word) + 1 > spec.max_prefixes:
            raise _Limit("Observed prefix count exceeds max_prefixes")
        for length in range(1, len(word) + 1):
            prefixes.add(word[:length])
            if len(prefixes) > spec.max_prefixes:
                raise _Limit("Observed prefix count exceeds max_prefixes")
    prefixes = tuple(sorted(prefixes))
    positions = {prefix: i for i, prefix in enumerate(prefixes)}
    index = {activity: i for i, activity in enumerate(alphabet)}
    counts = []
    for prefix in prefixes:
        count = [0] * n
        for activity in prefix:
            count[index[activity]] += 1
        counts.append(tuple(count))
    observed = tuple(
        (i, index[a])
        for i, prefix in enumerate(prefixes)
        for a in alphabet
        if prefix + (a,) in positions
    )
    targets = tuple(
        (i, index[a])
        for i, prefix in enumerate(prefixes)
        for a in alphabet
        if prefix + (a,) not in positions
    ) + tuple((i, None) for i, prefix in enumerate(prefixes) if prefix not in words)
    terminal = tuple(positions[word] for word in words)
    checks = 0

    def tick(amount=1):
        nonlocal checks
        checks += amount
        if checks > spec.max_region_checks:
            raise _Limit(
                "Region feasibility/separation checks exceed max_region_checks"
            )

    feasible = 0
    # Equivalent cover masks retain only their lexicographically cheapest
    # region. This is exact because any duplicate-mask region can be replaced.
    best = {}
    for vector in product(range(spec.max_arc_weight + 1), repeat=2 * n):
        consume, produce = vector[:n], vector[n:]
        difference = tuple(p - c for c, p in zip(consume, produce))
        offset = tuple(
            sum(a * b for a, b in zip(count, difference)) for count in counts
        )
        for initial in range(spec.max_observed_tokens + 1):
            tick(len(counts))
            markings = tuple(initial + delta for delta in offset)
            if any(m < 0 or m > spec.max_observed_tokens for m in markings):
                continue
            final = markings[terminal[0]]
            if any(markings[t] != final for t in terminal):
                continue
            tick(len(observed))
            if any(markings[i] < consume[a] for i, a in observed):
                continue
            feasible += 1
            tick(len(targets))
            blocked = tuple(
                j
                for j, (i, a) in enumerate(targets)
                if (markings[i] != final if a is None else markings[i] < consume[a])
            )
            if not blocked:
                continue
            mask = sum(1 << j for j in blocked)
            weight = initial + final + sum(consume) + sum(produce)
            region = IntegerRegion(initial, final, consume, produce, blocked, weight)
            key = (weight, initial, final, consume, produce)
            if mask not in best or key < best[mask][0]:
                best[mask] = key, region
    candidates = tuple((mask, pair[1]) for mask, pair in sorted(best.items()))
    return prefixes, targets, candidates, domain_size, feasible


def _minimum_cover(candidates, spec):
    target = 0
    for mask, _ in candidates:
        target |= mask
    if target == 0:
        return (), 0, 1
    covering = {}
    for i, (mask, _) in enumerate(candidates):
        rest = mask
        while rest:
            bit = rest & -rest
            covering.setdefault(bit, []).append(i)
            rest ^= bit
    # Dijkstra over coverage sets: positive integer arc-weight costs, then
    # place count. Branch on one uncovered obligation; every feasible cover
    # contains a region covering it, so this does not omit a feasible optimum.
    queue = [(0, 0, (), 0)]
    distances = {0: (0, 0, ())}
    checks = 0
    while queue:
        weight, count, selected, mask = heappop(queue)
        if distances.get(mask) != (weight, count, selected):
            continue
        if mask == target:
            return tuple(candidates[i][1] for i in selected), weight, len(distances)
        rest = target ^ mask
        choices = []
        while rest:
            bit = rest & -rest
            choices.append((len(covering[bit]), bit))
            rest ^= bit
        bit = min(choices)[1]
        for i in covering[bit]:
            checks += 1
            if checks > spec.max_optimizer_checks:
                raise _Limit("Exact region-cover search exceeds max_optimizer_checks")
            new_mask = mask | candidates[i][0]
            new_selected = tuple(sorted((*selected, i)))
            cost = weight + candidates[i][1].arc_weight_cost, count + 1, new_selected
            old = distances.get(new_mask)
            if old is None or cost < old:
                if old is None and len(distances) >= spec.max_optimizer_states:
                    raise _Limit(
                        "Exact region-cover search exceeds max_optimizer_states"
                    )
                distances[new_mask] = cost
                heappush(queue, (*cost, new_mask))
    raise AssertionError("union of available cover masks must be reachable")


def discover_regions(
    data: CaseInput,
    spec: RegionDiscoverySpec = RegionDiscoverySpec(),
) -> ComputationResult[RegionDiscovery]:
    """Synthesize a fitting accepting net under finite region/cover bounds.

    Negative extensions are candidates for restriction only. Unseparable
    extensions remain explicit in the payload and yield PARTIAL, although the
    optimal cover of all separable targets was solved completely. No observed
    trace is dropped. Counts do not change these language-based constraints.
    """
    if not isinstance(spec, RegionDiscoverySpec):
        raise TypeError("spec must be RegionDiscoverySpec")
    parent = as_case_traces(data, spec.trace_spec)
    operator = "pix.case_centric.discover_regions"

    def finish(status, value=None, issues=()):
        return _derived_result(
            operator,
            parent.source_digest,
            spec,
            status,
            value,
            parent.issues + tuple(issues),
            parent_computation_ids=(
                (parent.computation_id,) if parent.computation_id else ()
            ),
        )

    if parent.value is None:
        return finish(parent.status)
    if parent.status is not ComputeStatus.COMPUTED:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "incomplete_source",
                    "Region discovery requires a complete identified trace projection.",
                ),
            ),
        )
    words = frozenset(tuple(e.activity for e in t.events) for t in parent.value.traces)
    if not words:
        return finish(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "empty_log",
                    "At least one observed case is required; an empty case is permitted.",
                ),
            ),
        )
    alphabet = tuple(sorted({a for word in words for a in word}))
    try:
        prefixes, targets, candidates, assignments, feasible = _enumerate_regions(
            words, alphabet, spec
        )
        regions, cost, optimizer_states = _minimum_cover(candidates, spec)
    except _Limit as error:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("region_limit", str(error)),),
        )
    separated = {i for region in regions for i in region.blocked_target_ids}
    target_records = tuple(
        SeparationTarget(
            prefixes[i],
            None if a is None else alphabet[a],
            j in separated,
        )
        for j, (i, a) in enumerate(targets)
    )
    complete = len(separated) == len(targets)
    value = RegionDiscovery(
        _region_petri_net(alphabet, regions),
        alphabet,
        regions,
        target_records,
        assignments,
        feasible,
        optimizer_states,
        cost,
        len(regions),
        True,
        complete,
    )
    issues = (
        ()
        if complete
        else (
            ComputeIssue(
                "inseparable_extensions",
                "Some unobserved prefix extensions cannot be separated within the declared integer bounds; witnesses remain in separation_targets.",
            ),
        )
    )
    return finish(
        ComputeStatus.COMPUTED if complete else ComputeStatus.PARTIAL, value, issues
    )


RESULT_SCHEMAS = {
    "pix.case_centric.discover_regions": (
        "integer-region-discovery",
        RegionDiscoverySpec,
        RegionDiscovery,
    ),
}

__all__ = (
    "RegionDiscoverySpec",
    "RegionDiscovery",
    "IntegerRegion",
    "SeparationTarget",
    "discover_regions",
)
