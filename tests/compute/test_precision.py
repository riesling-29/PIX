"""Independent small-language answers for PIX enabled-prefix precision."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from random import Random

import pytest

from pix.compute._common import _result
from pix.compute.precision import measure_prefix_precision
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import ObjectTrace, TraceEvent, TraceSet, TraceSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.precision import PrefixPrecisionSpec
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.results import result_document, result_from_json, result_json_bytes


def traces(*sequences: str | tuple[str, ...]):
    value = TraceSet(
        "case",
        tuple(
            ObjectTrace(
                f"o{index}",
                "case",
                tuple(
                    TraceEvent(
                        f"e{index}-{position}",
                        activity,
                        datetime(2026, 1, 1, tzinfo=timezone.utc),
                        (),
                    )
                    for position, activity in enumerate(sequence)
                ),
            )
            for index, sequence in enumerate(sequences)
        ),
    )
    return _result(
        "pix.reconstruct_traces",
        None,
        TraceSpec("case"),
        ComputeStatus.COMPUTED,
        value,
        source_digest="precision-test-source",
    )


def state_net(edges, *, initial="i", final="f", extra_places=()):
    """Translate an independently specified finite-state machine into a net."""
    places = {initial, final, *extra_places}
    transitions = []
    arcs = []
    for index, (before, label, after) in enumerate(edges):
        places.update((before, after))
        transition_id = f"t{index}"
        transitions.append(Transition(transition_id, label))
        arcs.extend((Arc(before, transition_id), Arc(transition_id, after)))
    return PetriNet(
        tuple(Place(name) for name in sorted(places)),
        tuple(transitions),
        tuple(arcs),
        Marking(((initial, 1),)),
        Marking(((final, 1),)),
    )


def measure(net, *sequences, policy="include", cap=10000):
    return measure_prefix_precision(
        traces(*sequences), net, PrefixPrecisionSpec(policy, cap)
    )


def prefix(value, labels):
    return next(item for item in value.prefixes if item.prefix == tuple(labels))


@pytest.mark.parametrize("policy, expected", [("include", (2, 2)), ("exclude", (1, 1))])
def test_exact_single_activity(policy, expected):
    result = measure(state_net((("i", "A", "f"),)), "A", policy=policy)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.whole_log_ratio == expected
    assert result.value.coverage.requested_occurrences == (
        2 if policy == "include" else 1
    )


@pytest.mark.parametrize("policy, expected", [("include", (3, 4)), ("exclude", (2, 3))])
def test_duplicate_activity_branches_retain_all_markings(policy, expected):
    net = state_net(
        (("i", "A", "b"), ("i", "A", "c"), ("b", "B", "f"), ("c", "C", "f"))
    )
    result = measure(net, "AB", policy=policy)
    after_a = prefix(result.value, "A")
    assert after_a.reachable_markings == ((("b", 1),), (("c", 1),))
    assert after_a.enabled_labels == ("B", "C")
    assert after_a.escaping_labels == ("C",)
    assert result.value.whole_log_ratio == expected


@pytest.mark.parametrize(
    "policy, expected", [("include", (7, 11)), ("exclude", (3, 4))]
)
def test_shared_prefix_weight_excludes_only_terminal_visits(policy, expected):
    net = state_net((("i", "A", "f"), ("f", "B", "f"), ("f", "C", "f")))
    result = measure(net, "A", "AB", policy=policy)
    after_a = prefix(result.value, "A")
    assert (after_a.visit_count, after_a.extension_count, after_a.completion_count) == (
        2,
        1,
        1,
    )
    assert after_a.weight == (2 if policy == "include" else 1)
    assert result.value.whole_log_ratio == expected


def test_termination_disambiguates_model_a_or_ab_and_log_a():
    net = state_net((("i", "A", "f"), ("f", "B", "f")))
    included = measure(net, "A")
    excluded = measure(net, "A", policy="exclude")
    assert included.value.whole_log_ratio == (2, 3)
    assert excluded.value.whole_log_ratio == (1, 1)
    after_a = prefix(included.value, "A")
    assert after_a.enabled_termination is True
    assert after_a.enabled_labels == ("B",)
    assert after_a.escaping_labels == ("B",)


def test_completion_and_continuation_can_come_from_different_markings():
    net = state_net((("i", "A", "f"), ("i", "A", "j"), ("j", "B", "f")))
    result = measure(net, "A")
    after_a = prefix(result.value, "A")
    assert len(after_a.reachable_markings) == 2
    assert after_a.enabled_termination is True
    assert after_a.enabled_labels == ("B",)
    assert result.value.whole_log_ratio == (2, 3)


@pytest.mark.parametrize("policy, expected", [("include", (3, 6)), ("exclude", (2, 2))])
def test_repeat_language_completion_policy_is_visible(policy, expected):
    net = state_net((("f", "A", "f"),), initial="f")
    result = measure(net, "AA", policy=policy)
    assert result.value.whole_log_ratio == expected


def test_weighted_tokens_are_not_collapsed_to_place_presence():
    net = PetriNet(
        (Place("i"), Place("j"), Place("f")),
        (Transition("a", "A"), Transition("b", "B"), Transition("c", "C")),
        (
            Arc("i", "a"),
            Arc("a", "j", 2),
            Arc("j", "b", 2),
            Arc("b", "f"),
            Arc("j", "c", 3),
            Arc("c", "f"),
        ),
        Marking((("i", 1),)),
        Marking((("f", 1),)),
    )
    result = measure(net, "AB")
    assert prefix(result.value, "A").reachable_markings == ((("j", 2),),)
    assert prefix(result.value, "A").enabled_labels == ("B",)
    assert result.value.whole_log_ratio == (3, 3)


def test_exclude_measures_executability_not_accepting_fitness():
    net = state_net((("i", "A", "b"), ("b", "B", "f")))
    included = measure(net, "A")
    excluded = measure(net, "A", policy="exclude")
    assert included.status is ComputeStatus.PARTIAL
    assert included.value.whole_log_ratio is None
    assert included.value.completed_ratio == (1, 1)
    assert prefix(included.value, "A").missing_observed_termination is True
    assert excluded.status is ComputeStatus.COMPUTED
    assert excluded.value.whole_log_ratio == (1, 1)


def test_dead_end_behavior_is_counted_without_soundness_claim():
    net = state_net((("i", "A", "f"), ("i", "X", "dead")))
    result = measure(net, "A")
    assert result.value.whole_log_ratio == (2, 3)
    assert prefix(result.value, "").escaping_labels == ("X",)


def test_completion_is_not_a_reserved_activity_name():
    net = state_net((("i", "END", "f"), ("f", "END", "f")))
    result = measure(net, ("END",))
    after = prefix(result.value, ("END",))
    assert after.enabled_labels == ("END",)
    assert after.enabled_termination is True
    assert after.observed_labels == ()
    assert after.observed_termination is True
    assert after.enabled_option_count == 2
    assert result.value.whole_log_ratio == (2, 3)


def test_tau_closure_and_cycles_preserve_every_alternative():
    net = state_net(
        (("i", None, "j"), ("j", None, "i"), ("j", "A", "f"), ("i", "B", "f"))
    )
    result = measure(net, "A", cap=2)
    assert result.status is ComputeStatus.COMPUTED
    assert prefix(result.value, "").reachable_markings == ((("i", 1),), (("j", 1),))
    assert prefix(result.value, "").enabled_labels == ("A", "B")
    assert result.value.whole_log_ratio == (2, 3)


def test_exact_cap_silent_self_loop_completes():
    net = state_net((("i", None, "i"), ("i", "A", "f"), ("f", None, "f")))
    result = measure(net, "A", cap=1)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.whole_log_ratio == (2, 2)


def test_final_reachable_after_silent_moves_enables_termination():
    net = state_net((("i", "A", "j"), ("j", None, "f")))
    result = measure(net, "A")
    assert prefix(result.value, "A").enabled_termination is True
    assert result.value.whole_log_ratio == (2, 2)


def test_silent_unbounded_net_has_no_invented_precision():
    net = PetriNet(
        (Place("p"), Place("f")),
        (Transition("grow"), Transition("a", "A")),
        (Arc("p", "grow"), Arc("grow", "p", 2), Arc("p", "a"), Arc("a", "f")),
        Marking((("p", 1),)),
        Marking((("f", 1),)),
    )
    result = measure(net, "AA", cap=4)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.metric_status == "unavailable"
    assert result.value.whole_log_ratio is None
    assert result.value.completed_ratio is None
    assert [item.status for item in result.value.prefixes] == [
        "search_limit",
        "upstream_search_limit",
        "upstream_search_limit",
    ]
    assert all(item.enabled_labels is None for item in result.value.prefixes)
    assert result.value.coverage.search_limited_occurrences == 3


def test_synchronous_branch_count_also_respects_closure_bound():
    net = state_net((("i", "A", "j"), ("i", "A", "f")))
    result = measure(net, "A", cap=1)
    assert result.status is ComputeStatus.PARTIAL
    assert prefix(result.value, "").status == "computed"
    assert prefix(result.value, "A").status == "search_limit"
    assert result.value.completed_ratio == (1, 1)
    assert result.value.whole_log_ratio is None


def test_nonfitting_shared_root_retains_fitting_descendant_evidence():
    net = state_net((("i", "A", "f"),))
    result = measure(net, "A", "B")
    assert result.status is ComputeStatus.PARTIAL
    assert prefix(result.value, "").status == "unfit_observation"
    assert prefix(result.value, "").missing_observed_labels == ("B",)
    assert prefix(result.value, "A").status == "computed"
    assert prefix(result.value, "B").status == "unfit_prefix"
    assert result.value.coverage.unfit_occurrences == 3
    assert result.value.coverage.computed_occurrences == 1
    assert result.value.completed_ratio == (1, 1)
    assert result.value.whole_log_ratio is None


@pytest.mark.parametrize("sequences", [(), ("",), ("", "")])
@pytest.mark.parametrize("policy", ["include", "exclude"])
def test_empty_event_population_unavailable_never_one(sequences, policy):
    net = state_net((), initial="f", final="f")
    result = measure(net, *sequences, policy=policy)
    assert result.value.metric_status == "unavailable"
    assert result.value.whole_log_ratio is None
    assert result.value.completed_ratio is None
    assert result.value.coverage.empty_trace_count == len(sequences)
    assert any(
        issue.code == "precision_empty_event_population" for issue in result.issues
    )


def test_zero_denominator_nonfitting_population_is_unavailable():
    result = measure(state_net(()), "A", policy="exclude")
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.metric_status == "unavailable"
    assert result.value.completed_numerator == result.value.completed_denominator == 0
    assert result.value.completed_ratio is None
    assert any(issue.code == "precision_zero_denominator" for issue in result.issues)


def test_same_dfg_does_not_imply_same_prefix_observations():
    first = ("ABACA",)
    second = ("ACABA",)

    def edges(log):
        return Counter(pair for trace in log for pair in zip(trace, trace[1:]))

    assert edges(first) == edges(second)
    net = state_net(
        (
            ("i", "A", "j"),
            ("j", "B", "k"),
            ("k", "A", "l"),
            ("l", "C", "m"),
            ("m", "A", "f"),
        )
    )
    assert measure(net, *first).value.whole_log_ratio == (6, 6)
    second_result = measure(net, *second)
    assert second_result.status is ComputeStatus.PARTIAL
    assert second_result.value.whole_log_ratio is None
    assert prefix(second_result.value, "A").missing_observed_labels == ("C",)


def test_identical_transition_labels_count_once_but_all_markings_survive():
    net = state_net((("i", "A", "f"), ("i", "A", "f")))
    result = measure(net, "A")
    assert prefix(result.value, "").enabled_option_count == 1
    assert prefix(result.value, "A").reachable_markings == ((("f", 1),),)
    assert result.value.whole_log_ratio == (2, 2)


def test_population_replication_scales_integer_sums_not_ratio():
    net = state_net((("i", "A", "f"), ("f", "B", "f")))
    one = measure(net, "A").value
    three = measure(net, "A", "A", "A").value
    assert (one.completed_numerator, one.completed_denominator) == (2, 3)
    assert (three.completed_numerator, three.completed_denominator) == (6, 9)
    assert (
        three.coverage.requested_occurrences == 3 * one.coverage.requested_occurrences
    )


def test_explicit_profile_and_model_change_request_identity():
    net = state_net((("i", "A", "f"),))
    first = measure(net, "A")
    assert first.computation_id != measure(net, "A", policy="exclude").computation_id
    assert first.computation_id != measure(net, "A", cap=1).computation_id
    assert (
        first.computation_id
        != measure(state_net((("i", "B", "f"),)), "A").computation_id
    )
    assert first.parent_computation_ids == (traces("A").computation_id,)
    assert first.value.metric_profile == "pix.enabled_prefix_precision.v1"


@pytest.mark.parametrize(
    "status",
    [ComputeStatus.INVALID_INPUT, ComputeStatus.UNAVAILABLE, ComputeStatus.PARTIAL],
)
def test_upstream_diagnostics_preserved(status):
    source = traces("A")
    issue = ComputeIssue("original_problem", "original detail")
    source = replace(
        source,
        status=status,
        issues=(issue,),
        value=source.value if status is ComputeStatus.PARTIAL else None,
    )
    result = measure_prefix_precision(
        source, state_net((("i", "A", "f"),)), PrefixPrecisionSpec("include")
    )
    assert result.status is (
        ComputeStatus.INVALID_INPUT
        if status is ComputeStatus.INVALID_INPUT
        else ComputeStatus.UNAVAILABLE
    )
    assert result.value is None
    assert issue in result.issues


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"terminal_policy": "hidden"}, ValueError),
        ({"terminal_policy": "include", "max_markings_per_prefix": 0}, ValueError),
        ({"terminal_policy": "include", "max_markings_per_prefix": True}, TypeError),
        ({"terminal_policy": "include", "max_markings_per_prefix": 1.0}, TypeError),
        ({"terminal_policy": "include", "weighting": "uniform"}, ValueError),
    ],
)
def test_spec_rejects_ambiguous_or_invalid_parameters(kwargs, error):
    with pytest.raises(error):
        PrefixPrecisionSpec(**kwargs)


def test_terminal_policy_is_required():
    with pytest.raises(TypeError):
        PrefixPrecisionSpec()


@pytest.mark.parametrize("bad_argument", ["traces", "model", "spec"])
def test_operator_rejects_wrong_argument_types(bad_argument):
    arguments = [
        traces("A"),
        state_net((("i", "A", "f"),)),
        PrefixPrecisionSpec("include"),
    ]
    arguments[("traces", "model", "spec").index(bad_argument)] = None
    with pytest.raises(TypeError):
        measure_prefix_precision(*arguments)


def test_actual_tied_trace_order_warning_survives_successful_precision():
    timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    log = OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("case"),),
        events=(Event("e1", "A", timestamp), Event("e2", "B", timestamp)),
        objects=(Object("o1", "case"),),
        e2o=(E2O("e1", "o1", ""), E2O("e2", "o1", "")),
    )
    source = reconstruct_traces(log, TraceSpec("case", tie_policy="event_id"))
    assert source.status is ComputeStatus.COMPUTED
    assert any(issue.code == "timestamp_tie_broken" for issue in source.issues)
    result = measure_prefix_precision(
        source,
        state_net((("i", "A", "j"), ("j", "B", "f"))),
        PrefixPrecisionSpec("include"),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert all(issue in result.issues for issue in source.issues)
    assert result_from_json(result_json_bytes(result)) == result


def test_partial_precision_preserves_upstream_success_warning():
    issue = ComputeIssue("ordering_convention", "Event ID order is a convention")
    source = replace(traces("AB"), issues=(issue,))
    result = measure_prefix_precision(
        source, state_net((("i", "A", "f"),)), PrefixPrecisionSpec("include")
    )
    assert result.status is ComputeStatus.PARTIAL
    assert issue in result.issues
    assert any(item.code == "precision_unfit_prefix" for item in result.issues)


@pytest.mark.parametrize(
    "changes",
    [
        {"whole_log_ratio": (1, 1)},
        {"metric_status": "computed"},
        {"completed_ratio": (1, 0)},
        {"completed_ratio": (2, 1)},
        {"completed_ratio": (2, 2)},
        {"completed_numerator": 0},
        {"completed_denominator": 2},
        {"completed_numerator": True},
    ],
)
def test_precision_contract_rejects_contradictory_partial_aggregates(changes):
    value = measure(state_net((("i", "A", "f"),)), "AB").value
    with pytest.raises((TypeError, ValueError)):
        replace(value, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"requested_prefixes": 100},
        {"computed_occurrences": 100},
        {"empty_trace_count": 2},
        {"trace_count": -1},
        {"trace_count": True},
    ],
)
def test_coverage_contract_rejects_inconsistent_partitions(changes):
    value = measure(state_net((("i", "A", "f"),)), "AB").value
    with pytest.raises((TypeError, ValueError)):
        replace(value.coverage, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"visit_count": 2},
        {"weighted_enabled_options": 10},
        {"enabled_option_count": 10},
        {"escaping_labels": ("A",)},
        {"reachable_markings": ()},
        {"observed_termination": True},
        {"status": "search_limit"},
    ],
)
def test_evidence_contract_rejects_inconsistent_local_arithmetic(changes):
    value = measure(state_net((("i", "A", "f"),)), "A").value
    with pytest.raises((TypeError, ValueError)):
        replace(value.prefixes[0], **changes)


def _resigned_precision(document):
    body = {key: value for key, value in document.items() if key != "document_digest"}
    serialized = json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    document["document_digest"] = (
        "pix.analysis-result.v1:sha256:" + sha256(serialized).hexdigest()
    )
    return json.dumps(document)


@pytest.mark.parametrize(
    "path,new_value",
    [
        (("whole_log_ratio",), [1, 1]),
        (("metric_status",), "computed"),
        (("completed_ratio",), [1, 0]),
        (("completed_numerator",), 2),
        (("coverage", "event_occurrence_count"), 99),
        (("coverage", "requested_prefixes"), 99),
        (("prefixes", 0, "weighted_enabled_options"), 99),
        (("prefixes", 0, "enabled_option_count"), 99),
        (("prefixes", 1, "weighted_enabled_options"), 1),
    ],
)
def test_resigned_json_rejects_contradictory_precision_evidence(path, new_value):
    result = measure(state_net((("i", "A", "f"),)), "AB")
    document = result_document(result)
    node = document["computation"]["value"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = new_value
    with pytest.raises((TypeError, ValueError)):
        result_from_json(_resigned_precision(document))


def test_writer_revalidates_payload_bypassing_frozen_dataclass():
    result = measure(state_net((("i", "A", "f"),)), "AB")
    object.__setattr__(result.value, "whole_log_ratio", (1, 1))
    with pytest.raises(ValueError, match="whole-log ratio"):
        result_json_bytes(result)


def _nfa_oracle(edges, sequences, policy):
    """Independent finite-state closure and prefix arithmetic, no PIX semantics."""
    observations = {}
    weights = Counter()
    termination = set()
    for sequence in sequences:
        for index in range(len(sequence) + 1):
            p = sequence[:index]
            observations.setdefault(p, set())
            if index < len(sequence):
                observations[p].add(sequence[index])
            else:
                termination.add(p)
            if policy == "include" or index < len(sequence):
                weights[p] += 1
    states_by_prefix = {}
    details = {}
    numerator = denominator = 0
    incomplete = False
    for p in sorted(observations, key=lambda value: (len(value), value)):
        states = (
            {"i"}
            if not p
            else {
                target
                for start, label, target in edges
                if start in states_by_prefix[p[:-1]] and label == p[-1]
            }
        )
        while True:
            expanded = states | {
                target
                for start, label, target in edges
                if start in states and label is None
            }
            if expanded == states:
                break
            states = expanded
        states_by_prefix[p] = states
        if not weights[p]:
            continue
        enabled = {
            label
            for start, label, target in edges
            if start in states and label is not None
        }
        model_end = "f" in states and policy == "include"
        log_end = p in termination and policy == "include"
        unfit = (
            not states or bool(observations[p] - enabled) or (log_end and not model_end)
        )
        details[p] = (enabled, model_end, unfit, states)
        if unfit:
            incomplete = True
        else:
            denominator += weights[p] * (len(enabled) + int(model_end))
            numerator += weights[p] * (
                len(enabled & observations[p]) + int(model_end and log_end)
            )
    ratio = (numerator, denominator) if denominator and any(sequences) else None
    return numerator, denominator, None if incomplete else ratio, details


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("policy", ["include", "exclude"])
def test_finite_state_oracle(seed, policy):
    rng = Random(seed)
    states = ("i", "j", "f")
    edges = tuple(
        (a, label, b)
        for a in states
        for label in (None, "A", "B")
        for b in states
        if rng.random() < 0.2
    )
    sequences = tuple(
        tuple(rng.choice(("A", "B")) for _ in range(rng.randrange(4))) for _ in range(4)
    )
    expected_n, expected_d, expected_whole, details = _nfa_oracle(
        edges, sequences, policy
    )
    result = measure(state_net(edges), *sequences, policy=policy)
    assert result.value.completed_numerator == expected_n
    assert result.value.completed_denominator == expected_d
    assert result.value.whole_log_ratio == expected_whole
    coverage = result.value.coverage
    assert (
        coverage.requested_prefixes
        == coverage.computed_prefixes
        + coverage.unfit_prefixes
        + coverage.search_limited_prefixes
    )
    assert (
        coverage.requested_occurrences
        == coverage.computed_occurrences
        + coverage.unfit_occurrences
        + coverage.search_limited_occurrences
    )
    for p, (enabled, model_end, unfit, states) in details.items():
        record = prefix(result.value, p)
        assert set(record.enabled_labels) == enabled
        assert record.enabled_termination == model_end
        assert (record.status in ("unfit_prefix", "unfit_observation")) == unfit
        assert {marking[0][0] for marking in record.reachable_markings} == states
