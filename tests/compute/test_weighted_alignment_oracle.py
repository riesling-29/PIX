"""Bounded acyclic multi-token PN language oracle, independent of PIX firing.

Literal token arithmetic enumerates all accepting words; an independent edit
DP gives unit log/model move cost. No claim about arbitrary unbounded nets.
"""

import json
from collections import deque
from itertools import product

import pytest

from pix.compute.conformance import align_traces
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.event_log import case_log_from_activity_text, case_traces


def language(transitions):
    start, final = (2, 0, 0, 0, 0, 0), (0, 0, 0, 0, 0, 2)
    queue = deque([(start, ())])
    seen = set()
    words = set()
    while queue:
        marking, word = queue.popleft()
        if (marking, word) in seen:
            continue
        seen.add((marking, word))
        assert len(seen) < 100, "oracle incomplete: finite bound exceeded"
        if marking == final:
            words.add(word)
        for label, consume, produce in transitions:
            if all(marking[i] >= v for i, v in consume):
                out = list(marking)
                for i, v in consume:
                    out[i] -= v
                for i, v in produce:
                    out[i] += v
                assert all(0 <= v <= 2 for v in out), "oracle bound invalid"
                queue.append(
                    (tuple(out), word + ((label,) if label is not None else ()))
                )
    return words


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        nxt = [i]
        for j, y in enumerate(b, 1):
            nxt.append(min(row[j] + 1, nxt[-1] + 1, row[j - 1] + (0 if x == y else 2)))
        row = nxt
    return row[-1]


@pytest.mark.parametrize("duplicate", [False, True])
def test_parallel_weighted_join_matches_independent_language(duplicate):
    transitions = (
        (None, ((0, 2),), ((1, 1), (2, 1))),
        ("A", ((1, 1),), ((3, 1),)),
        ("A" if duplicate else "B", ((2, 1),), ((4, 1),)),
        (None, ((3, 1), (4, 1)), ((5, 2),)),
    )
    words = language(transitions)
    assert words == ({("A", "A")} if duplicate else {("A", "B"), ("B", "A")})
    arcs = []
    for i, (_, consume, produce) in enumerate(transitions):
        arcs.extend(Arc(f"p{p}", f"t{i}", v) for p, v in consume)
        arcs.extend(Arc(f"t{i}", f"p{p}", v) for p, v in produce)
    net = PetriNet(
        tuple(Place(f"p{i}") for i in range(6)),
        tuple(Transition(f"t{i}", t[0]) for i, t in enumerate(transitions)),
        tuple(arcs),
        Marking((("p0", 2),)),
        Marking((("p5", 2),)),
    )
    for length in range(4):
        for sequence in product(("A", "B"), repeat=length):
            traces = case_traces(case_log_from_activity_text(json.dumps([sequence])))
            result = align_traces(traces, net)
            assert result.value.alignments[0].cost == min(
                distance(sequence, w) for w in words
            )
            assert result.value.alignments[0].status == "optimal"
