"""Independent matching oracles and contextual/privacy-boundary regressions.

Deterministic sampler substitutions verify arithmetic only, never privacy.
Finite tests are not a privacy certificate for the floating-point time channels.
"""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import permutations, product
from math import exp, isclose

import pytest

from pix.case_centric import pripel
from pix.case_centric.pripel import (
    PripelAttributeDomain,
    PripelSpec,
    reconstruct_pripel_context,
)
from pix.case_centric.privacy import (
    PrivateVariantCount,
    TraceVariantRelease,
    privacy_release,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def query(*words):
    counts = {}
    for word in words:
        counts[tuple(word)] = counts.get(tuple(word), 0) + 1
    return TraceVariantRelease(
        "synthetic-test-query-no-dp-claim",
        "test-fixture",
        "not-certified",
        "add_remove_case",
        1.0,
        0.0,
        ("A", "B", "X", "a", "b", "OTHER"),
        "OTHER",
        5,
        0,
        (),
        tuple(PrivateVariantCount(word, count) for word, count in counts.items()),
    )


def request(*words, **changes):
    return PripelSpec(
        **dict(
            dict(
                query=query(*words),
                timestamp_lower=START,
                timestamp_upper=START + timedelta(seconds=100),
            ),
            **changes,
        )
    )


def source(*words, attributes=(), times=None):
    return CaseLog(
        tuple(
            CaseTrace(
                f"private-case-{i}",
                tuple(
                    CaseEvent(
                        f"private-event-{i}-{j}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute(
                                "time:timestamp",
                                "date",
                                START
                                + timedelta(
                                    seconds=(j + 1) * 10
                                    if times is None
                                    else times[i][j]
                                ),
                            ),
                            *attributes,
                        ),
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def zero_noise(monkeypatch):
    monkeypatch.setattr(pripel, "_laplace", lambda scale: 0.0)
    monkeypatch.setattr(
        pripel, "_randomized_response", lambda value, values, epsilon: value
    )


def words(result):
    return tuple(
        tuple(event.activity for event in trace.events)
        for trace in result.value.synthetic_log.traces
    )


def brute_assignment(cost):
    rows, columns = len(cost), len(cost[0])
    if rows <= columns:
        return min(
            sum(cost[i][j] for i, j in enumerate(chosen))
            for chosen in permutations(range(columns), rows)
        )
    return min(
        sum(cost[i][j] for j, i in enumerate(chosen))
        for chosen in permutations(range(rows), columns)
    )


@pytest.mark.parametrize("rows,columns", [(1, 3), (3, 1), (2, 3), (3, 2), (3, 3)])
def test_hungarian_matches_exhaustive_injective_oracle(rows, columns):
    for entries in product(range(3), repeat=rows * columns):
        costs = tuple(
            tuple(entries[i * columns : (i + 1) * columns]) for i in range(rows)
        )
        pairs = pripel._assignment(costs)
        assert len(pairs) == min(rows, columns)
        assert len({i for i, j in pairs}) == len(pairs)
        assert len({j for i, j in pairs}) == len(pairs)
        assert sum(costs[i][j] for i, j in pairs) == brute_assignment(costs)


def test_assignment_empty_and_ties_are_deterministic():
    assert pripel._assignment(()) == ()
    assert pripel._assignment(((),)) == ()
    assert pripel._assignment(((0, 0), (0, 0))) == ((0, 0), (1, 1))


def recursive_edit(left, right):
    if not left or not right:
        return len(left) + len(right)
    return min(
        recursive_edit(left[1:], right) + 1,
        recursive_edit(left, right[1:]) + 1,
        recursive_edit(left[1:], right[1:]) + (left[0] != right[0]),
    )


def test_edit_distance_matches_independent_recursive_definition():
    language = tuple(
        word for size in range(4) for word in product(("A", "B"), repeat=size)
    )
    for left, right in product(language, repeat=2):
        assert pripel._edit_distance(left, right) == recursive_edit(left, right)
    assert pripel._edit_distance(("A@B",), ("A", "B")) == 2


def test_matching_amplification_counterexample(monkeypatch):
    zero_noise(monkeypatch)
    base = source(("X", "a", "b"), ("X", "a", "a", "a"))

    def with_flag(trace, flag):
        return replace(
            trace,
            events=tuple(
                replace(
                    event,
                    attributes=event.attributes
                    + (CaseAttribute("flag", "boolean", flag),),
                )
                for event in trace.events
            ),
        )

    left = CaseLog((with_flag(base.traces[0], True), with_flag(base.traces[1], False)))
    added = source(("X", "b"))
    added_trace = replace(
        added.traces[0],
        id="added-case",
        events=tuple(
            replace(event, id=f"added-{i}")
            for i, event in enumerate(added.traces[0].events)
        ),
    )
    right = CaseLog((*left.traces, with_flag(added_trace, False)))
    spec = request(
        ("X", "a"), ("X", "b"), attributes=(PripelAttributeDomain("flag", "boolean"),)
    )
    before, after = (
        reconstruct_pripel_context(left, spec),
        reconstruct_pripel_context(right, spec),
    )
    assert [
        (row.source_case_id, row.edit_distance) for row in before.value.matches
    ] == [("private-case-1", 2), ("private-case-0", 1)]
    assert [(row.source_case_id, row.edit_distance) for row in after.value.matches] == [
        ("private-case-0", 1),
        ("added-case", 0),
    ]
    assert tuple(
        t.events[0].attribute("flag").value for t in before.value.synthetic_log.traces
    ) == (False, True)
    assert tuple(
        t.events[0].attribute("flag").value for t in after.value.synthetic_log.traces
    ) == (True, False)
    # If each output bit were epsilon-RR, this neighbor ratio would be e^(2eps).
    eps = 0.7
    p = exp(eps) / (1 + exp(eps))
    assert isclose(p * p / ((1 - p) * (1 - p)), exp(2 * eps))
    assert before.value.coordinate_count == 8  # ALL 4 events x (timestamp + bool).
    assert before.value.epsilon_per_coordinate == 0.125


def test_matching_enrichment_repeated_occurrences(monkeypatch):
    zero_noise(monkeypatch)
    base = source(("A", "B", "A"))
    events = tuple(
        replace(
            event,
            attributes=event.attributes + (CaseAttribute("amount", "int", amount),),
        )
        for event, amount in zip(base.traces[0].events, (11, 22, 33))
    )
    base = CaseLog((replace(base.traces[0], events=events),))
    spec = request(
        ("A", "A", "B"),
        attributes=(PripelAttributeDomain("amount", "numerical", lower=0, upper=100),),
    )
    actual = reconstruct_pripel_context(base, spec)
    assert actual.status is ComputeStatus.COMPUTED
    output = actual.value.synthetic_log.traces[0].events
    assert [event.attribute("amount").value for event in output] == [11.0, 33.0, 22.0]
    assert [event.timestamp for event in output] == [
        START + timedelta(seconds=t) for t in (10, 30, 40)
    ]
    assert actual.value.matches[0].edit_distance == 2
    assert base.traces[0].events == events  # Source was not mutated.


def test_timestamps_noise_start_and_each_gap_not_only_common_shift(monkeypatch):
    noises, scales = iter((2.0, 3.0)), []

    def laplace(scale):
        scales.append(scale)
        return next(noises)

    monkeypatch.setattr(pripel, "_laplace", laplace)
    result = reconstruct_pripel_context(
        source(("A", "B")), request(("A", "B"), epsilon_context=2.0)
    )
    events = result.value.synthetic_log.traces[0].events
    assert [event.timestamp for event in events] == [
        START + timedelta(seconds=t) for t in (12, 25)
    ]
    assert (events[1].timestamp - events[0].timestamp).total_seconds() == 13
    assert scales == [100.0, 100.0]


def test_public_bounds_clipping_and_nondecreasing_timestamps(monkeypatch):
    zero_noise(monkeypatch)
    domain = PripelAttributeDomain("n", "numerical", lower=0, upper=5)
    actual = reconstruct_pripel_context(
        source(
            ("A", "B", "A"),
            attributes=(CaseAttribute("n", "int", 90),),
            times=((-20, 200, -5),),
        ),
        request(("A", "B", "A"), attributes=(domain,)),
    )
    events = actual.value.synthetic_log.traces[0].events
    assert [event.attribute("n").value for event in events] == [5.0, 5.0, 5.0]
    assert [event.timestamp for event in events] == [
        START,
        START + timedelta(seconds=100),
        START + timedelta(seconds=100),
    ]


def test_unmatched_cases_unknown_activities_and_empty_variants_preserved(monkeypatch):
    zero_noise(monkeypatch)
    spec = request(("OTHER",), ("A",), (), ("B", "B"))
    actual = reconstruct_pripel_context(source(("secret unknown activity",)), spec)
    assert words(actual) == (("OTHER",), ("A",), (), ("B", "B"))
    assert sum(row.source_case_id is not None for row in actual.value.matches) == 1
    assert actual.value.matches[0].edit_distance == 0
    assert sum(len(trace.events) for trace in actual.value.synthetic_log.traces) == 4


def test_public_schema_fills_missing_and_drops_unlisted_fields(monkeypatch):
    zero_noise(monkeypatch)
    monkeypatch.setattr(pripel.secrets, "randbelow", lambda n: 0)
    domains = (
        PripelAttributeDomain("group", "categorical", values=("red", "blue")),
        PripelAttributeDomain("flag", "boolean"),
        PripelAttributeDomain("amount", "numerical", lower=2, upper=2),
    )
    actual = reconstruct_pripel_context(
        source(
            ("A",),
            attributes=(
                CaseAttribute("private_customer", "string", "Alice"),
                CaseAttribute("group", "string", "outside"),
            ),
        ),
        request(("A",), attributes=domains),
    )
    attrs = actual.value.synthetic_log.traces[0].events[0].attributes
    assert [(a.key, a.value) for a in attrs[2:]] == [
        ("group", "red"),
        ("flag", False),
        ("amount", 2.0),
    ]
    assert {a.key for a in attrs} == {
        "concept:name",
        "time:timestamp",
        "group",
        "flag",
        "amount",
    }
    assert "Alice" not in repr(actual.value.synthetic_log)
    assert "private-case-0" in repr(actual.value.matches)
    assert actual.value.synthetic_log.source is None


def test_empty_source_has_public_fallback_context(monkeypatch):
    zero_noise(monkeypatch)
    actual = reconstruct_pripel_context(CaseLog(), request(("A", "B")))
    assert actual.status is ComputeStatus.COMPUTED
    assert actual.value.matches[0].source_case_id is None
    assert [e.timestamp for e in actual.value.synthetic_log.traces[0].events] == [
        START,
        START,
    ]


def test_empty_query_has_no_channels(monkeypatch):
    monkeypatch.setattr(
        pripel, "_laplace", lambda scale: pytest.fail("empty output used noise")
    )
    actual = reconstruct_pripel_context(source(("A",)), request())
    assert actual.value.synthetic_log.traces == ()
    assert actual.value.matches == ()
    assert actual.value.coordinate_count == 0
    assert actual.value.epsilon_context_allocated == 0


def test_all_empty_traces_and_length_zero_query(monkeypatch):
    zero_noise(monkeypatch)
    spec = replace(request((), ()), query=replace(query((), ()), max_trace_length=0))
    actual = reconstruct_pripel_context(source(("A",), ()), spec)
    assert words(actual) == ((), ())
    assert all(row.edit_distance == 0 for row in actual.value.matches)
    assert actual.value.coordinate_count == 0


def test_missing_timestamps_are_synthetic_fallback_not_observed_facts(monkeypatch):
    zero_noise(monkeypatch)
    log = CaseLog(
        (
            CaseTrace(
                "t", (CaseEvent("e", (CaseAttribute("concept:name", "string", "A"),)),)
            ),
        )
    )
    actual = reconstruct_pripel_context(log, request(("A",)))
    assert actual.value.synthetic_log.traces[0].events[0].timestamp == START
    assert "unknown_timestamp" in {issue.code for issue in actual.issues}
    assert log.traces[0].events[0].timestamp is None


def test_source_clipping_and_generated_identity_do_not_copy_original_ids(monkeypatch):
    zero_noise(monkeypatch)
    spec = replace(request(("A",)), query=replace(query(("A",)), max_trace_length=1))
    actual = reconstruct_pripel_context(source(("A", "B", "B")), spec)
    assert actual.value.matches[0].edit_distance == 0
    output = actual.value.synthetic_log
    assert output.traces[0].id.startswith("pripel-")
    assert output.traces[0].events[0].id.startswith("pripel-")
    assert "private-event" not in repr(output)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"max_source_traces": 1}, "pripel_matching_limit"),
        ({"max_matrix_cells": 1}, "pripel_matching_limit"),
        ({"max_edit_cells": 1}, "pripel_edit_limit"),
    ],
)
def test_resource_limits_never_return_truncated_success(changes, code):
    actual = reconstruct_pripel_context(
        source(("A",), ("B",)), request(("A",), **changes)
    )
    assert actual.status is ComputeStatus.UNAVAILABLE and actual.value is None
    assert code in {issue.code for issue in actual.issues}


def test_invalid_mapping_propagates_without_claiming_output():
    invalid = CaseLog((CaseTrace("t", (CaseEvent("e"),)),))
    actual = reconstruct_pripel_context(invalid, request(("A",)))
    assert actual.status is ComputeStatus.UNAVAILABLE
    assert actual.value is None


def test_budget_exactly_bounds_all_coordinates_and_query_changes_identity(monkeypatch):
    zero_noise(monkeypatch)
    spec = request(("A", "A", "A"), epsilon_context=0.1)
    actual = reconstruct_pripel_context(source(("A",)), spec)
    assert Fraction(actual.value.epsilon_per_coordinate) * 3 <= Fraction(
        spec.epsilon_context
    )
    assert actual.source_digest is not None and actual.parent_computation_ids
    changed = reconstruct_pripel_context(
        source(("A",)), request(("B", "B", "B"), epsilon_context=0.1)
    )
    assert actual.computation_id != changed.computation_id


def test_private_only_boundary_and_immutable_output(monkeypatch):
    zero_noise(monkeypatch)
    actual = reconstruct_pripel_context(source(("A",)), request(("A",)))
    assert actual.value.release_policy == "private_analysis_only"
    assert "not_certified" in actual.value.privacy_model
    assert "pripel_private_diagnostics_only" in {issue.code for issue in actual.issues}
    with pytest.raises(ValueError):
        privacy_release(actual)
    with pytest.raises(FrozenInstanceError):
        actual.value.release_policy = "publish"
    assert pripel.RESULT_SCHEMAS[pripel.OPERATOR_ID] == (
        "pripel-context-result",
        PripelSpec,
        type(actual.value),
    )


@pytest.mark.parametrize("epsilon", [1e-100, 0.01, 0.1, 1.0, 20.0, 200.0])
def test_rational_response_weights_have_conservative_likelihood_ratio(epsilon):
    keep, other = pripel._response_weights(3, epsilon)
    assert keep >= other >= 1
    # High precision independent Decimal comparator; epsilon < 1e-70 is uniform.
    with localcontext() as context:
        context.prec = 120
        assert (Decimal(keep) / Decimal(other)).ln() <= Decimal.from_float(epsilon)


def test_randomized_response_integer_intervals_cover_all_categories(monkeypatch):
    keep, other = pripel._response_weights(3, 1.0)
    for draw, expected in [
        (0, "B"),
        (keep - 1, "B"),
        (keep, "A"),
        (keep + other - 1, "A"),
        (keep + other, "C"),
        (keep + 2 * other - 1, "C"),
    ]:
        monkeypatch.setattr(pripel.secrets, "randbelow", lambda n, draw=draw: draw)
        assert pripel._randomized_response("B", ("A", "B", "C"), 1.0) == expected
    assert pripel._randomized_response("A", ("A",), 1.0) == "A"


def test_secure_float_sampler_has_open_endpoints_and_clips_overflow(monkeypatch):
    monkeypatch.setattr(pripel.secrets, "randbelow", lambda n: 0)
    assert 0 < pripel._uniform_open() < 1
    assert pripel._laplace(1.0) < 0
    monkeypatch.setattr(pripel.secrets, "randbelow", lambda n: n - 1)
    assert 0 < pripel._uniform_open() < 1
    assert pripel._laplace(1.0) > 0
    monkeypatch.setattr(pripel, "_laplace", lambda scale: float("inf"))
    assert pripel._noisy_number(0.0, 0.0, 10.0, 1.0) == 10.0
    monkeypatch.setattr(pripel, "_laplace", lambda scale: float("-inf"))
    assert pripel._noisy_number(0.0, 0.0, 10.0, 1.0) == 0.0


@pytest.mark.parametrize(
    "changes",
    [
        {"epsilon_context": 0},
        {"epsilon_context": True},
        {"epsilon_context": float("nan")},
        {"epsilon_context": 10**10000},
        {"epsilon_context": 5e-324},
        {"timestamp_lower": datetime(2026, 1, 1)},
        {"timestamp_upper": START},
        {"attributes": []},
        {"release_policy": "safe_to_publish"},
        {"max_target_traces": 0},
        {"max_source_traces": False},
        {"trace_spec": "source_order"},
    ],
)
def test_invalid_specs_rejected(changes):
    with pytest.raises((ValueError, TypeError)):
        request(("A", "B"), **changes)


@pytest.mark.parametrize(
    "domain",
    [
        dict(key="concept:name", kind="categorical", values=("A",)),
        dict(key="x", kind="categorical", values=()),
        dict(key="x", kind="categorical", values=("A", "A")),
        dict(key="x", kind="categorical", values=["A"]),
        dict(key="x", kind="boolean", values=("A",)),
        dict(key="x", kind="numerical", lower=2, upper=1),
        dict(key="x", kind="numerical", lower=-1e308, upper=1e308),
        dict(key="x", kind="numerical", upper=float("inf")),
        dict(key="x", kind="unsupported"),
    ],
)
def test_invalid_public_domains_rejected(domain):
    with pytest.raises((ValueError, TypeError)):
        PripelAttributeDomain(**domain)


@pytest.mark.parametrize(
    "changes",
    [
        {"variants": (PrivateVariantCount(("A",), -1),)},
        {"variants": (PrivateVariantCount(("A",), True),)},
        {"variants": (PrivateVariantCount(("not_public",), 1),)},
        {"variants": (PrivateVariantCount(("A",), 1), PrivateVariantCount(("A",), 1))},
        {"variants": (PrivateVariantCount(("A",), 201),)},
        {"max_trace_length": 0},
        {"epsilon_budget": float("nan")},
        {"public_activities": ["A", "OTHER"]},
        {"other_activity": "missing"},
        {"release_nonce": []},
        {"depths": []},
    ],
)
def test_malformed_query_rejected_without_authenticating_privacy(changes):
    with pytest.raises((ValueError, TypeError)):
        request(("A",), query=replace(query(("A",)), **changes))


def test_invalid_log_and_spec_types_rejected():
    with pytest.raises(TypeError):
        reconstruct_pripel_context([], request())
    with pytest.raises(TypeError):
        reconstruct_pripel_context(CaseLog(), None)


@pytest.mark.parametrize(
    "lower,upper",
    [
        (START, datetime.max.replace(tzinfo=timezone.utc)),
        (
            datetime.min.replace(tzinfo=timezone.utc),
            datetime(9998, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
        ),
        (
            datetime.min.replace(tzinfo=timezone.utc),
            datetime.max.replace(tzinfo=timezone.utc),
        ),
    ],
)
def test_broad_datetime_bounds_use_exact_final_microsecond_clamp(
    monkeypatch, lower, upper
):
    monkeypatch.setattr(pripel, "_laplace", lambda scale: float("inf"))
    actual = reconstruct_pripel_context(
        CaseLog(), request(("A",), timestamp_lower=lower, timestamp_upper=upper)
    )
    assert actual.value.synthetic_log.traces[0].events[0].timestamp == upper


def test_nested_query_numbers_normalized_for_spec_roundtrip():
    from pix.case_centric.privacy import PrivacyDepth
    from pix.results import _decode, _encode

    raw = replace(
        query(("A",)),
        epsilon_budget=1,
        epsilon_allocated=0,
        depths=(PrivacyDepth(1, 1, 1, 1, None, None),),
    )
    spec = request(("A",), query=raw)
    assert type(spec.query.epsilon_budget) is float
    assert type(spec.query.depths[0].epsilon_allocated) is float
    assert (
        _decode(_encode(spec, large_integers=True), PripelSpec, large_integers=True)
        == spec
    )


def test_context_payload_roundtrip_preserves_tagged_case_attributes(monkeypatch):
    from pix.results import _decode, _encode

    zero_noise(monkeypatch)
    actual = reconstruct_pripel_context(
        source(("A",)),
        request(
            ("A",),
            attributes=(
                PripelAttributeDomain("n", "numerical"),
                PripelAttributeDomain("flag", "boolean"),
                PripelAttributeDomain(
                    "category", "categorical", values=("2026-01-01T00:00:00.000000Z",)
                ),
            ),
        ),
    )
    assert (
        _decode(
            _encode(actual.value, large_integers=True),
            pripel.PripelContextResult,
            large_integers=True,
        )
        == actual.value
    )


def test_genuine_sacofa_to_pripel_pipeline_and_composed_budget(monkeypatch):
    from pix.case_centric import sacofa
    from pix.case_centric.privacy import TraceVariantPrivacySpec
    from pix.results import _decode, _encode

    zero_noise(monkeypatch)
    monkeypatch.setattr(sacofa, "_sample_discrete_laplace", lambda q: 0)
    log = source(("A", "B"), ("A",))
    control = sacofa.anonymize_sacofa(
        log,
        sacofa.SACOFASpec(
            TraceVariantPrivacySpec(
                activities=("A", "B"),
                other_activity="A",
                max_trace_length=2,
                epsilon=3.0,
            ),
            sacofa.SACOFASemantics(activities=("A", "B")),
        ),
    )
    assert control.status is ComputeStatus.COMPUTED
    spec = request(query=control.value, epsilon_context=0.1)
    actual = reconstruct_pripel_context(log, spec)
    assert words(actual) == (("A",), ("A", "B"))
    assert actual.value.epsilon_control_flow_bound == 3.0
    assert Fraction(actual.value.epsilon_composed_ideal_bound) >= Fraction(
        3.0
    ) + Fraction(0.1)
    assert (
        Fraction(actual.value.epsilon_context_allocated)
        >= Fraction(actual.value.epsilon_per_coordinate) * 3
    )
    assert actual.value.epsilon_context_allocated <= spec.epsilon_context
    assert (
        _decode(_encode(spec, large_integers=True), PripelSpec, large_integers=True)
        == spec
    )


def test_coordinate_resource_limit_and_composed_overflow_rejected():
    with pytest.raises(ValueError, match="max_output_scalars"):
        request(("A", "B"), max_output_scalars=1)
    with pytest.raises(ValueError, match="composed privacy budget"):
        request(
            ("A",),
            epsilon_context=1.7e308,
            query=replace(query(("A",)), epsilon_budget=1.7e308),
        )
