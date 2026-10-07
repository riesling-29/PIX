"""Discovery acceptance checks from OCEL facts and independent net reachability.

These tests exercise the documented conservative cut miner, not IM parity.
The fitting oracle follows arcs and visible transition labels; it does not
reproduce the miner's cuts or use alignment to decide whether a trace fits.
"""

from collections import Counter, defaultdict, deque
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import combinations, product

import pytest

from pix.compute.dfg import discover_dfg
from pix.compute.discovery import discover_process_tree, process_tree_to_petri_net
from pix.compute.model_semantics import enabled_transitions, fire
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import ObjectTrace, TraceEvent, TraceSet, TraceSpec
from pix.contracts.discovery import DiscoverySpec, ProcessTree
from pix.contracts.models import Marking
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _log(*traces: str) -> OCEL:
    """One object per trace, with isolated objects representing epsilon."""
    events = tuple(
        Event(
            f"e{case:03d}_{index:03d}",
            activity,
            ORIGIN + timedelta(seconds=index),
        )
        for case, trace in enumerate(traces)
        for index, activity in enumerate(trace)
    )
    return OCEL(
        event_types=tuple(EventType(a) for a in sorted(set("".join(traces)))),
        object_types=(ObjectType("case"),),
        objects=tuple(Object(f"o{case:03d}", "case") for case in range(len(traces))),
        events=events,
        e2o=tuple(
            E2O(f"e{case:03d}_{index:03d}", f"o{case:03d}", "flow")
            for case, trace in enumerate(traces)
            for index in range(len(trace))
        ),
    )


def _discover(*traces: str, spec: DiscoverySpec | None = None):
    trace_result = reconstruct_traces(_log(*traces), TraceSpec("case"))
    assert trace_result.status is ComputeStatus.COMPUTED
    return discover_process_tree(trace_result, spec or DiscoverySpec())


def _independent_steps(net, tokens):
    """Apply plain weighted P/T equations directly, independently of PIX firing."""
    counts = dict(tokens)
    for transition in net.transitions:
        inputs = {a.source: a.weight for a in net.arcs if a.target == transition.id}
        if not all(counts.get(place, 0) >= weight for place, weight in inputs.items()):
            continue
        after = Counter(counts)
        after.subtract(inputs)
        after.update(
            {a.target: a.weight for a in net.arcs if a.source == transition.id}
        )
        yield transition, tuple(sorted((p, n) for p, n in after.items() if n))


def _accepts(net, trace: str) -> bool:
    pending = deque([(net.initial_marking.tokens, 0)])
    visited = set(pending)
    while pending:
        tokens, offset = pending.popleft()
        if tokens == net.final_marking.tokens and offset == len(trace):
            return True
        for transition, after in _independent_steps(net, tokens):
            if transition.activity is None:
                next_offset = offset
            elif offset < len(trace) and transition.activity == trace[offset]:
                next_offset = offset + 1
            else:
                continue
            state = after, next_offset
            if state not in visited:
                assert len(visited) < 5000, "bounded acceptance oracle exhausted"
                visited.add(state)
                pending.append(state)
    return False


def _assert_sound_small_net(net):
    """Check all reachable markings for these finite, small workflow nets."""
    initial, final = net.initial_marking.tokens, net.final_marking.tokens
    visited = {initial}
    pending = [initial]
    predecessors = defaultdict(set)
    fired = set()
    sink = next(iter(dict(final)))
    while pending:
        tokens = pending.pop()
        independent = {t.id: after for t, after in _independent_steps(net, tokens)}
        marking = Marking(tokens)
        assert set(enabled_transitions(net, marking)) == set(independent)
        for transition_id, after in independent.items():
            assert fire(net, marking, transition_id).tokens == after
            predecessors[after].add(tokens)
            fired.add(transition_id)
            if after not in visited:
                assert len(visited) < 2000, "bounded soundness oracle exhausted"
                visited.add(after)
                pending.append(after)
        if dict(tokens).get(sink, 0):
            assert tokens == final, "completion must not leave residual tokens"
    assert final in visited
    assert not list(_independent_steps(net, final))
    can_finish = {final}
    pending = [final]
    while pending:
        for previous in predecessors[pending.pop()] - can_finish:
            can_finish.add(previous)
            pending.append(previous)
    assert can_finish == visited, "every reachable state must retain a completion"
    assert fired == {t.id for t in net.transitions}, "no transition may be dead"


@pytest.mark.parametrize(
    ("traces", "operator", "accepted", "rejected"),
    [
        (("ABC",), "sequence", ("ABC",), ("", "ACB", "AB", "ABBC")),
        (("AB", "CD"), "xor", ("AB", "CD"), ("", "AC", "ABCD")),
        (("AB", "BA"), "parallel", ("AB", "BA"), ("", "A", "AA", "ABA")),
        (("AB", "ABRAB"), "loop", ("AB", "ABRAB", "ABRABRAB"), ("", "R", "ARB")),
        (("AAA",), "loop", ("A", "AAA", "AAAA"), ("", "B")),
        (("ABAB",), "loop", ("AB", "ABAB", "ABABAB"), ("", "A", "ABA", "BA")),
        (("", "AB"), "xor", ("", "AB"), ("A", "BA", "ABAB")),
    ],
)
def test_discovered_basic_behavior_is_executable_and_sound(
    traces, operator, accepted, rejected
):
    result = _discover(*traces)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == operator
    assert not result.issues
    net = process_tree_to_petri_net(result.value)
    for trace in accepted:
        assert _accepts(net, trace), (traces, trace, result.value)
    for trace in rejected:
        assert not _accepts(net, trace), (traces, trace, result.value)
    _assert_sound_small_net(net)


def test_no_objects_is_unavailable_while_an_isolated_object_is_silent_behavior():
    absent = _discover()
    assert absent.status is ComputeStatus.UNAVAILABLE
    assert absent.value is None
    assert [issue.code for issue in absent.issues] == ["empty_population"]
    isolated = _discover("")
    assert isolated.status is ComputeStatus.COMPUTED
    assert isolated.value == ProcessTree("tau")
    net = process_tree_to_petri_net(isolated.value)
    assert _accepts(net, "")
    assert not _accepts(net, "A")
    _assert_sound_small_net(net)


def test_upstream_ties_remain_unavailable_until_order_policy_is_selected():
    log = _log("AB")
    tied = replace(
        log, events=tuple(replace(event, time=ORIGIN) for event in log.events)
    )
    upstream = reconstruct_traces(tied, TraceSpec("case"))
    rejected = discover_process_tree(upstream, DiscoverySpec())
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.value is None
    assert {i.code for i in rejected.issues} == {
        "upstream_not_computed",
        "ambiguous_event_order",
    }
    assert rejected.parent_computation_ids == (upstream.computation_id,)
    explicit = reconstruct_traces(tied, TraceSpec("case", tie_policy="event_id"))
    accepted = discover_process_tree(explicit, DiscoverySpec())
    assert accepted.status is ComputeStatus.COMPUTED
    assert _accepts(process_tree_to_petri_net(accepted.value), "AB")


def test_invalid_upstream_is_not_an_empty_discovered_model():
    upstream = reconstruct_traces(None, TraceSpec("case"))
    result = discover_process_tree(upstream, DiscoverySpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.source_digest is result.computation_id is None
    assert result.parent_computation_ids == ()
    assert result.issues[0].code == "upstream_not_computed"


def test_invalid_ocel_causes_survive_trace_and_discovery_without_status_downgrade():
    invalid = replace(_log("AB"), e2o=(E2O("missing_event", "missing_object", "flow"),))
    upstream = reconstruct_traces(invalid, TraceSpec("case"))
    assert upstream.status is ComputeStatus.INVALID_INPUT
    assert {issue.code for issue in upstream.issues} == {
        "dangling_e2o_event",
        "dangling_e2o_object",
    }
    result = discover_process_tree(upstream, DiscoverySpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[1:] == upstream.issues
    assert "invalid_input" in result.issues[0].message
    assert result.source_digest is result.computation_id is None
    assert result.parent_computation_ids == ()


def test_unknown_object_selection_retains_cause_location_and_parent_identity():
    upstream = reconstruct_traces(_log("AB"), TraceSpec("unknown"))
    assert upstream.status is ComputeStatus.UNAVAILABLE
    result = discover_process_tree(upstream, DiscoverySpec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[1:] == upstream.issues
    assert result.issues[1].code == "unknown_object_type"
    assert result.issues[1].at == ("object_type", "unknown")
    assert "unavailable" in result.issues[0].message
    assert result.source_digest == upstream.source_digest
    assert result.parent_computation_ids == (upstream.computation_id,)


def test_partial_trace_population_is_not_presented_as_complete_discovery():
    upstream = reconstruct_traces(_log("AB"), TraceSpec("case"))
    partial = replace(
        upstream,
        status=ComputeStatus.PARTIAL,
        issues=(
            ComputeIssue("population_incomplete", "A source partition is unavailable"),
        ),
    )
    result = discover_process_tree(partial, DiscoverySpec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.parent_computation_ids == (partial.computation_id,)
    assert "population_incomplete" in {issue.code for issue in result.issues}
    assert result.issues[1:] == partial.issues
    assert "partial" in result.issues[0].message


@pytest.mark.parametrize("algorithm", ["pix.inductive_cut.v1", "pix.im.v1"])
def test_actual_timestamp_tie_convention_evidence_survives_discovery(algorithm):
    log = _log("AB")
    tied = replace(
        log, events=tuple(replace(event, time=ORIGIN) for event in log.events)
    )
    upstream = reconstruct_traces(tied, TraceSpec("case", tie_policy="event_id"))
    assert upstream.status is ComputeStatus.COMPUTED
    assert "timestamp_tie_broken" in {issue.code for issue in upstream.issues}
    result = discover_process_tree(upstream, DiscoverySpec(algorithm=algorithm))
    assert result.status is ComputeStatus.COMPUTED
    assert result.issues == upstream.issues
    assert result.parent_computation_ids == (upstream.computation_id,)
    assert _accepts(process_tree_to_petri_net(result.value), "AB")


@pytest.mark.parametrize("algorithm", ["pix.inductive_cut.v1", "pix.im.v1"])
def test_successful_upstream_diagnostics_survive_discovery_and_depth_limits(algorithm):
    upstream = reconstruct_traces(_log("ABC"), TraceSpec("case"))
    warning = ComputeIssue(
        "source_policy_note",
        "Source trace was computed under an explicit convention",
        ("trace",),
    )
    annotated = replace(upstream, issues=(warning,))
    result = discover_process_tree(annotated, DiscoverySpec(algorithm=algorithm))
    assert result.status is ComputeStatus.COMPUTED
    assert result.issues == (warning,)
    assert result.parent_computation_ids == (upstream.computation_id,)
    limited = discover_process_tree(
        annotated, DiscoverySpec(algorithm=algorithm, max_depth=1)
    )
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None
    assert limited.issues[0].code == "discovery_depth_limit"
    assert limited.issues[1:] == (warning,)


@pytest.mark.parametrize("corruption", ["duplicate_object", "wrong_type", "bad_event"])
def test_malformed_nested_trace_payload_does_not_escape_as_a_computed_model(corruption):
    upstream = reconstruct_traces(_log("AB"), TraceSpec("case"))
    trace = upstream.value.traces[0]
    if corruption == "duplicate_object":
        traces = (trace, trace)
    elif corruption == "wrong_type":
        traces = (ObjectTrace(trace.object_id, "other", trace.events),)
    else:
        traces = (
            ObjectTrace(
                trace.object_id, trace.object_type, (TraceEvent("bad", "", ORIGIN, ()),)
            ),
        )
    malformed = replace(upstream, value=TraceSet("case", traces))
    result = discover_process_tree(malformed, DiscoverySpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "invalid_trace_input"


def test_dfg_is_rejected_without_silent_conversion_to_a_different_algorithm():
    dfg = discover_dfg(_log("ABC"), TraceSpec("case"))
    result = discover_process_tree(dfg, DiscoverySpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "trace_input_required"
    assert result.source_digest == dfg.source_digest
    assert result.parent_computation_ids == (dfg.computation_id,)


def test_discovery_preserves_source_and_parent_request_identity():
    log = _log("AB")
    first_parent = reconstruct_traces(log, TraceSpec("case"))
    second_parent = reconstruct_traces(log, TraceSpec("case", qualifiers=("flow",)))
    first = discover_process_tree(first_parent, DiscoverySpec())
    second = discover_process_tree(second_parent, DiscoverySpec())
    assert first.value == second.value
    assert first.source_digest == first_parent.source_digest == second.source_digest
    assert first.parent_computation_ids == (first_parent.computation_id,)
    assert second.parent_computation_ids == (second_parent.computation_id,)
    assert first.computation_id != second.computation_id
    assert first.operator_id == "pix.discover_process_tree"


def test_collection_order_does_not_change_tree_model_or_computation_identity():
    log = _log("ABC", "ACB", "ABD", "ADB")
    permuted = replace(
        log,
        event_types=log.event_types[::-1],
        events=log.events[::-1],
        objects=log.objects[::-1],
        e2o=log.e2o[::-1],
    )
    first = discover_process_tree(
        reconstruct_traces(log, TraceSpec("case")), DiscoverySpec()
    )
    second = discover_process_tree(
        reconstruct_traces(permuted, TraceSpec("case")), DiscoverySpec()
    )
    assert first == second
    assert process_tree_to_petri_net(first.value) == process_tree_to_petri_net(
        second.value
    )


def test_same_dfg_different_whole_traces_retain_distinct_discovery_lineage():
    left, right = _log("ABC", "DBE"), _log("ABE", "DBC")

    def signature(log):
        graph = discover_dfg(log, TraceSpec("case")).value
        return (
            tuple(
                (e.source_activity, e.target_activity, e.occurrence_count)
                for e in graph.edges
            ),
            tuple((e.activity, len(e.evidence)) for e in graph.starts),
            tuple((e.activity, len(e.evidence)) for e in graph.ends),
        )

    assert signature(left) == signature(right)
    first_parent = reconstruct_traces(left, TraceSpec("case"))
    second_parent = reconstruct_traces(right, TraceSpec("case"))
    first = discover_process_tree(first_parent, DiscoverySpec())
    second = discover_process_tree(second_parent, DiscoverySpec())
    assert first.status is second.status is ComputeStatus.COMPUTED
    assert first.source_digest != second.source_digest
    assert first.parent_computation_ids != second.parent_computation_ids
    assert first.computation_id != second.computation_id
    assert all(
        _accepts(process_tree_to_petri_net(first.value), t) for t in ("ABC", "DBE")
    )
    assert all(
        _accepts(process_tree_to_petri_net(second.value), t) for t in ("ABE", "DBC")
    )


def test_explicit_depth_limit_returns_no_partial_model():
    result = _discover("ABC", spec=DiscoverySpec(max_depth=1))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "discovery_depth_limit"


def test_no_supported_cut_reports_its_flower_generalization_explicitly():
    result = _discover("AB", "ACBCA")
    assert result.status is ComputeStatus.COMPUTED
    assert [issue.code for issue in result.issues] == ["flower_fallthrough"]
    net = process_tree_to_petri_net(result.value)
    for trace in ("AB", "ACBCA", "C", "BBBB", "CAB"):
        assert _accepts(net, trace)
    assert not _accepts(net, "")
    _assert_sound_small_net(net)


@pytest.mark.parametrize("algorithm", ["IM", "IMf", "IMd", "inductive", ""])
def test_unsupported_algorithms_are_not_aliased_to_the_native_cut_miner(algorithm):
    with pytest.raises(ValueError):
        DiscoverySpec(algorithm=algorithm)


@pytest.mark.parametrize("noise", [0.1, -0.1, float("inf"), float("nan")])
def test_nonzero_or_nonfinite_noise_cannot_silently_change_behavior(noise):
    with pytest.raises(ValueError):
        DiscoverySpec(noise_threshold=noise)


@pytest.mark.parametrize(
    "parameters",
    [
        {"algorithm": None},
        {"noise_threshold": True},
        {"noise_threshold": "0"},
        {"max_depth": True},
    ],
)
def test_invalid_request_types_fail_at_the_contract_boundary(parameters):
    with pytest.raises(TypeError):
        DiscoverySpec(**parameters)


def test_contract_is_immutable_and_public_functions_reject_wrong_arguments():
    with pytest.raises(FrozenInstanceError):
        DiscoverySpec().algorithm = "IM"
    with pytest.raises(TypeError):
        discover_process_tree(_log("AB"), DiscoverySpec())
    with pytest.raises(TypeError):
        discover_process_tree(reconstruct_traces(_log("AB"), TraceSpec("case")), None)
    with pytest.raises(TypeError):
        process_tree_to_petri_net(None)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operator": "unknown"},
        {"operator": "activity", "activity": "\ud800"},
        {"operator": "tau", "activity": "A"},
        {"operator": "loop", "children": (ProcessTree("tau"),)},
        {"operator": "sequence", "children": (ProcessTree("tau"),)},
    ],
)
def test_invalid_process_tree_semantics_fail_before_model_conversion(kwargs):
    with pytest.raises(ValueError):
        ProcessTree(**kwargs)


def test_external_process_tree_depth_is_checked_before_recursive_sorting():
    tree = ProcessTree("activity", "A")
    for _ in range(300):
        tree = ProcessTree("xor", children=(tree, ProcessTree("tau")))
    with pytest.raises(ValueError, match="depth 128"):
        process_tree_to_petri_net(tree)


def test_repeated_activity_leaves_have_separate_executable_transition_identities():
    tree = ProcessTree(
        "sequence",
        children=(
            ProcessTree("activity", "A"),
            ProcessTree("activity", "A"),
            ProcessTree("activity", "B"),
        ),
    )
    net = process_tree_to_petri_net(tree)
    a_transitions = [t for t in net.transitions if t.activity == "A"]
    assert len(a_transitions) == len({t.id for t in a_transitions}) == 2
    assert _accepts(net, "AAB")
    assert not _accepts(net, "AB")
    _assert_sound_small_net(net)


def test_nested_parallel_choice_and_loop_are_sound_and_preserve_hand_checked_behavior():
    def leaf(label):
        return ProcessTree("activity", label)

    tree = ProcessTree(
        "sequence",
        children=(
            ProcessTree(
                "parallel",
                children=(
                    ProcessTree("xor", children=(leaf("A"), ProcessTree("tau"))),
                    ProcessTree("loop", children=(leaf("B"), leaf("R"))),
                ),
            ),
            leaf("C"),
        ),
    )
    net = process_tree_to_petri_net(tree)
    for trace in ("BC", "ABC", "BAC", "BRBAC", "ABRBRC"):
        # ABRBRC omits the required final do after redo.
        assert _accepts(net, trace) is (trace != "ABRBRC")
    for trace in ("", "C", "AC", "CB", "AABC", "BRRC"):
        assert not _accepts(net, trace)
    _assert_sound_small_net(net)


def test_bounded_exhaustive_observed_trace_fitting_without_cut_specific_oracles():
    # All 105 unordered distinct pairs from epsilon and A/B words up to length 3,
    # plus every A/B/C singleton word up to length 4 (120). Zero noise promises
    # to admit each observation, even where the selected abstraction generalizes.
    binary_words = [""] + [
        "".join(word) for length in range(1, 4) for word in product("AB", repeat=length)
    ]
    populations = list(combinations(binary_words, 2))
    populations.extend(
        ("".join(word),)
        for length in range(1, 5)
        for word in product("ABC", repeat=length)
    )
    for traces in populations:
        result = _discover(*traces)
        assert result.status is ComputeStatus.COMPUTED, (traces, result.issues)
        net = process_tree_to_petri_net(result.value)
        for trace in traces:
            assert _accepts(net, trace), (traces, trace, result.value)
