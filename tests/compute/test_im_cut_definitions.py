"""Independent, bounded definition oracle for the four formal IM cuts.

The oracle enumerates partitions instead of reproducing the production cut
algorithms. It checks Definitions 5--8 of the 19-page PN2013 author manuscript:
https://leemans.ch/publications/papers/pn2013leemans.pdf (pp. 11--14), SHA256
9bdb53177e1c8552004c73cc2445b21dbfab8bc0f93551fe8af39e989214b953.

That manuscript's sequence definition has two reachability conditions. The
additional boundary condition in a separate technical report is not used.
The epsilon witness guard belongs to PIX's explicitly documented practical
profile, not the original paper's treatment of a mixed empty/nonempty log.
"""

from collections import deque
from functools import cache
from itertools import permutations, product
from random import Random

import pytest

from pix.compute.discovery import (
    _im_cut,
    _im_loop_groups,
    _im_parallel_groups,
    _sequence_groups,
)

OPERATORS = ("xor", "sequence", "parallel", "loop")


@cache
def _partitions(activities):
    """Enumerate every unordered partition, including the trivial partition."""
    if not activities:
        return ((),)
    first, *remaining = activities
    result = []
    for groups in _partitions(tuple(remaining)):
        result.append((frozenset((first,)), *groups))
        for index, group in enumerate(groups):
            result.append(groups[:index] + (group | {first},) + groups[index + 1 :])
    return tuple(result)


def _reachability(activities, edges):
    """Independent graph search; a node reaches itself only through a cycle."""
    result = {}
    for source in activities:
        reached = set()
        pending = [target for start, target in edges if start == source]
        while pending:
            current = pending.pop()
            if current not in reached:
                reached.add(current)
                pending.extend(target for start, target in edges if start == current)
        result[source] = reached
    return result


def _satisfies_definition(operator, groups, edges, starts, ends, reachable):
    if operator == "xor":
        return all(
            (a, b) not in edges
            for i, left in enumerate(groups)
            for j, right in enumerate(groups)
            if i != j
            for a in left
            for b in right
        )
    if operator == "sequence":
        return all(
            b in reachable[a] and a not in reachable[b]
            for i, left in enumerate(groups)
            for right in groups[i + 1 :]
            for a in left
            for b in right
        )
    if operator == "parallel":
        return all(group & starts and group & ends for group in groups) and all(
            (a, b) in edges
            for i, left in enumerate(groups)
            for j, right in enumerate(groups)
            if i != j
            for a in left
            for b in right
        )

    assert operator == "loop"
    body, *redo = groups
    # Definition 8.1: every observed boundary activity belongs to the body.
    if not (starts | ends) <= body:
        return False
    for branch in redo:
        for activity in branch:
            # 8.2--8.3: every body/redo edge respects its boundary role.
            for body_activity in body:
                if (body_activity, activity) in edges and body_activity not in ends:
                    return False
                if (activity, body_activity) in edges and body_activity not in starts:
                    return False
            # 8.5--8.6: completeness covers ALL starts/ends, not just one.
            if any((activity, a) in edges for a in body) and any(
                (activity, start) not in edges for start in starts
            ):
                return False
            if any((a, activity) in edges for a in body) and any(
                (end, activity) not in edges for end in ends
            ):
                return False
    # 8.4: separate redo branches never have a directly-follows edge.
    return all(
        (a, b) not in edges
        for i, left in enumerate(redo)
        for j, right in enumerate(redo)
        if i != j
        for a in left
        for b in right
    )


@cache
def _edge_only_maxima(activities, edges):
    reachable = _reachability(activities, edges)
    maxima = {"xor": 0, "sequence": 0}
    for groups in _partitions(activities):
        if len(groups) < 2:
            continue
        if _satisfies_definition("xor", groups, edges, set(), set(), reachable):
            maxima["xor"] = max(maxima["xor"], len(groups))
        for ordered in permutations(groups):
            if _satisfies_definition(
                "sequence", ordered, edges, set(), set(), reachable
            ):
                maxima["sequence"] = max(maxima["sequence"], len(groups))
    return maxima, reachable


def _definition_oracle(activities, edges, starts, ends):
    base, reachable = _edge_only_maxima(tuple(sorted(activities)), frozenset(edges))
    maxima = dict(base, parallel=0, loop=0)
    for groups in _partitions(tuple(sorted(activities))):
        if len(groups) < 2:
            continue
        if _satisfies_definition("parallel", groups, edges, starts, ends, reachable):
            maxima["parallel"] = max(maxima["parallel"], len(groups))
        # Only the body is distinguished; redo branch ordering has no meaning.
        for body_index in range(len(groups)):
            ordered = (
                groups[body_index],
                *groups[:body_index],
                *groups[body_index + 1 :],
            )
            if _satisfies_definition("loop", ordered, edges, starts, ends, reachable):
                maxima["loop"] = max(maxima["loop"], len(groups))
    return maxima, reachable


def _context(log):
    return (
        frozenset(activity for trace in log for activity in trace),
        frozenset((a, b) for trace in log for a, b in zip(trace, trace[1:])),
        frozenset(trace[0] for trace in log),
        frozenset(trace[-1] for trace in log),
    )


def _path(edges, sources, targets):
    pending = deque((source, (source,)) for source in sorted(sources))
    visited = set(sources)
    while pending:
        current, trace = pending.popleft()
        if current in targets:
            return trace
        for target in sorted(b for a, b in edges if a == current):
            if target not in visited:
                visited.add(target)
                pending.append((target, trace + (target,)))
    return None


def _realize_context(activities, edges, starts, ends):
    """Construct actual traces with exactly the requested graph and boundaries.

    Every activity must be reachable from a start and able to reach an end.
    Under that condition, each edge can be embedded in a start-to-end trace.
    Additional traces make each requested start and end observable.
    """
    traces = set()
    for activity in activities:
        prefix = _path(edges, starts, {activity})
        suffix = _path(edges, {activity}, ends)
        if prefix is None or suffix is None:
            return None
        traces.add(prefix + suffix[1:])
    for start in starts:
        traces.add(_path(edges, {start}, ends))
    for end in ends:
        traces.add(_path(edges, starts, {end}))
    for source, target in edges:
        # Concatenation includes the selected edge, including self-loops.
        traces.add(_path(edges, starts, {source}) + _path(edges, {target}, ends))
    return tuple(sorted(traces))


def _assert_cut_is_maximal(operator, groups, context, maxima, reachable, log):
    activities, edges, starts, ends = context
    nontrivial_count = len(groups) if len(groups) > 1 else 0
    explanation = (operator, log, groups, maxima)
    assert nontrivial_count == maxima[operator], explanation
    if nontrivial_count:
        assert all(groups), explanation
        assert set().union(*groups) == activities, explanation
        assert sum(map(len, groups)) == len(activities), explanation
        assert _satisfies_definition(
            operator, groups, edges, starts, ends, reachable
        ), explanation


def _assert_matches_oracle(log):
    context = _context(log)
    activities, edges, starts, ends = context
    maxima, reachable = _definition_oracle(*context)
    detected = {
        "sequence": _sequence_groups(activities, edges),
        "parallel": _im_parallel_groups(activities, edges, starts, ends),
        "loop": _im_loop_groups(activities, edges, starts, ends),
    }
    for operator, groups in detected.items():
        _assert_cut_is_maximal(operator, groups, context, maxima, reachable, log)

    expected = next((operator for operator in OPERATORS if maxima[operator]), None)
    actual = _im_cut(log)
    assert (actual[0] if actual else None) == expected, (log, actual, maxima)
    if actual:
        _assert_cut_is_maximal(*actual, context, maxima, reachable, log)


@pytest.mark.parametrize("size, expected_contexts", [(1, 2), (2, 72), (3, 12848)])
def test_all_realizable_small_graph_contexts_match_formal_cut_definitions(
    size, expected_contexts
):
    activities = tuple("ABC"[:size])
    possible_edges = tuple(product(activities, repeat=2))
    nonempty_subsets = tuple(
        frozenset(a for index, a in enumerate(activities) if mask & (1 << index))
        for mask in range(1, 1 << size)
    )
    checked = 0
    for edge_mask in range(1 << len(possible_edges)):
        edges = frozenset(
            edge
            for index, edge in enumerate(possible_edges)
            if edge_mask & (1 << index)
        )
        for starts, ends in product(nonempty_subsets, repeat=2):
            log = _realize_context(activities, edges, starts, ends)
            if log is None:
                continue
            assert _context(log) == (frozenset(activities), edges, starts, ends)
            _assert_matches_oracle(log)
            checked += 1
    # Guard the scope of this exhaustive enumeration against accidental shrinkage.
    assert checked == expected_contexts


def test_seeded_four_activity_contexts_match_formal_cut_definitions():
    random = Random(9140)
    checked = set()
    for _ in range(2000):
        log = tuple(
            sorted(
                {
                    tuple(random.choice("ABCD") for _ in range(random.randrange(1, 9)))
                    for _ in range(random.randrange(1, 9))
                }
            )
        )
        context = _context(log)
        if context[0] != frozenset("ABCD") or context in checked:
            continue
        _assert_matches_oracle(log)
        checked.add(context)
        if len(checked) == 200:
            break
    assert len(checked) == 200


@pytest.mark.parametrize(
    "log",
    [(), ((),), ((), ("A", "B"), ("A", "C")), ((), ("A",), ("B",))],
)
def test_activity_removal_cut_witness_rejects_empty_trace(log):
    # Epsilon must not be discarded to manufacture a structural-cut witness.
    # The nonempty remainders in the last cases DO have structural cuts.
    assert _im_cut(log) is None
    nonempty = tuple(trace for trace in log if trace)
    if nonempty:
        assert _im_cut(nonempty) is not None
