"""Independent finite-trace formulas and hand-calculated temporal populations."""

from datetime import datetime, timedelta, timezone
from itertools import product
from math import sqrt

import pytest

from pix.case_centric.declarative import (
    DECLARE_TEMPLATES,
    ActivityFrequency,
    DeclareConformanceSpec,
    DeclareConstraint,
    DeclareDiscoverySpec,
    DeclareModel,
    FootprintConformanceSpec,
    FootprintReference,
    LogSkeleton,
    LogSkeletonSpec,
    SkeletonRelation,
    TemporalConformanceSpec,
    TemporalProfile,
    TemporalProfileEntry,
    TemporalProfileSpec,
    check_declare,
    check_footprints,
    check_log_skeleton,
    check_temporal_profile,
    discover_declare,
    discover_log_skeleton,
    discover_temporal_profile,
    footprint_reference,
)
from pix.contracts.result import ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def log_of(*sequences, times=None, starts=None):
    traces = []
    for case_index, sequence in enumerate(sequences):
        events = []
        for event_index, activity in enumerate(sequence):
            attributes = [CaseAttribute("concept:name", "string", activity)]
            value = event_index if times is None else times[case_index][event_index]
            if value is not None:
                stamp = (
                    value
                    if isinstance(value, datetime)
                    else BASE + timedelta(seconds=value)
                )
                attributes.append(CaseAttribute("time:timestamp", "date", stamp))
            if starts is not None and starts[case_index][event_index] is not None:
                attributes.append(
                    CaseAttribute(
                        "start",
                        "date",
                        BASE + timedelta(seconds=starts[case_index][event_index]),
                    )
                )
            events.append(CaseEvent(f"c{case_index}:e{event_index}", tuple(attributes)))
        traces.append(CaseTrace(f"c{case_index}", tuple(events)))
    return CaseLog(tuple(traces))


def formula(sequence, template):
    """A separate truth-table oracle, with no calls into PIX rule evaluators."""
    count_a, count_b = sequence.count("A"), sequence.count("B")
    a = [i for i, x in enumerate(sequence) if x == "A"]
    b = [i for i, x in enumerate(sequence) if x == "B"]
    response = all(
        any(sequence[j] == "B" for j in range(i + 1, len(sequence))) for i in a
    )
    precedence = all("A" in sequence[:i] for i in b)
    # Alternate rules can be checked on the projection's adjacent relevant
    # events. Chain rules use the ORIGINAL event sequence instead.
    projected = "".join(x for x in sequence if x in "AB")
    alt_response = all(
        i + 1 < len(projected) and projected[i + 1] == "B"
        for i, x in enumerate(projected)
        if x == "A"
    )
    alt_precedence = all(
        i > 0 and projected[i - 1] == "A" for i, x in enumerate(projected) if x == "B"
    )
    chain_response = all(sequence[i : i + 2] == "AB" for i in a)
    chain_precedence = all(i > 0 and sequence[i - 1 : i + 1] == "AB" for i in b)
    values = {
        "existence": count_a >= 1,
        "absence": count_a < 1,
        "exactly": count_a == 1,
        "exactly_one": count_a == 1,
        "init": sequence.startswith("A"),
        "end": sequence.endswith("A"),
        "responded_existence": not count_a or bool(count_b),
        "response": response,
        "precedence": precedence,
        "alternate_response": alt_response,
        "alternate_precedence": alt_precedence,
        "chain_response": chain_response,
        "chain_precedence": chain_precedence,
        "succession": response and precedence,
        "alternate_succession": alt_response and alt_precedence,
        "chain_succession": chain_response and chain_precedence,
        "coexistence": bool(count_a) == bool(count_b),
        "noncoexistence": not (count_a and count_b),
        "not_response": not any(i < j for i in a for j in b),
        "not_precedence": not any(i < j for i in a for j in b),
        "nonsuccession": not any(i < j for i in a for j in b),
        "nonchainsuccession": "AB" not in sequence,
    }
    return bool(values[template])


SEQUENCES = tuple(
    "".join(xs) for length in range(7) for xs in product("ABC", repeat=length)
)
UNARY = {"existence", "absence", "exactly", "exactly_one", "init", "end"}


@pytest.mark.parametrize("template", DECLARE_TEMPLATES)
def test_all_closed_templates_against_independent_truth_table(template):
    rule = DeclareConstraint(template, "A", None if template in UNARY else "B")
    model = DeclareModel(("A", "B"), (rule,))
    result = check_declare(log_of(*SEQUENCES), model)
    assert result.status is ComputeStatus.COMPUTED
    assert len(result.value.evaluations) == len(SEQUENCES)
    for sequence, evaluation in zip(SEQUENCES, result.value.evaluations):
        assert (evaluation.state != "violated") == formula(sequence, template), (
            template,
            sequence,
            evaluation,
        )
        assert all(x.state in ("satisfied", "violated") for x in evaluation.obligations)


@pytest.mark.parametrize(
    "name,canonical",
    [
        ("altresponse", "alternate_response"),
        ("altprecedence", "alternate_precedence"),
        ("altsuccession", "alternate_succession"),
        ("chainresponse", "chain_response"),
        ("chainprecedence", "chain_precedence"),
        ("chainsuccession", "chain_succession"),
    ],
)
def test_reference_template_aliases_normalize(name, canonical):
    assert DeclareConstraint(name, "A", "B").template == canonical


@pytest.mark.parametrize(
    "template", ["response", "alternate_response", "chain_response"]
)
def test_open_case_tracks_every_activation_and_irreversible_failures(template):
    result = check_declare(
        log_of("AA"),
        DeclareModel(("A", "B"), (DeclareConstraint(template, "A", "B"),)),
        DeclareConformanceSpec(observation="open"),
    )
    assert result.status is ComputeStatus.PARTIAL
    evaluation = result.value.evaluations[0]
    assert tuple(x.activation_index for x in evaluation.obligations) == (0, 1)
    expected_first = "pending" if template == "response" else "violated"
    assert tuple(x.state for x in evaluation.obligations) == (expected_first, "pending")
    assert evaluation.state == ("pending" if template == "response" else "violated")


def test_vacuity_and_closed_failure_are_distinct():
    model = DeclareModel(("A", "B"), (DeclareConstraint("response", "A", "B"),))
    closed = check_declare(log_of("", "B", "A", "AAB"), model).value
    assert tuple(x.state for x in closed.evaluations) == (
        "vacuous",
        "vacuous",
        "violated",
        "satisfied",
    )
    obligations = closed.evaluations[-1].obligations
    assert tuple(x.activation_index for x in obligations) == (0, 1)
    assert tuple(x.witness_indices for x in obligations) == ((2,), (2,))


@pytest.mark.parametrize("template", DECLARE_TEMPLATES)
def test_open_violation_cannot_be_repaired_by_bounded_future_suffix(template):
    prefixes = tuple(
        "".join(xs) for length in range(5) for xs in product("ABC", repeat=length)
    )
    suffixes = tuple(
        "".join(xs) for length in range(4) for xs in product("ABC", repeat=length)
    )
    model = DeclareModel(
        ("A", "B"),
        (DeclareConstraint(template, "A", None if template in UNARY else "B"),),
    )
    opened = check_declare(
        log_of(*prefixes), model, DeclareConformanceSpec(observation="open")
    )
    for prefix, evaluation in zip(prefixes, opened.value.evaluations):
        if evaluation.state == "violated":
            for suffix in suffixes:
                assert not formula(prefix + suffix, template), (
                    template,
                    prefix,
                    suffix,
                )


def test_open_satisfied_means_observed_obligations_not_future_guarantee():
    model = DeclareModel(("A", "B"), (DeclareConstraint("response", "A", "B"),))
    first = check_declare(
        log_of("AB"), model, DeclareConformanceSpec(observation="open")
    )
    assert first.value.evaluations[0].state == "satisfied"
    extended = check_declare(
        log_of("ABA"), model, DeclareConformanceSpec(observation="open")
    )
    assert extended.value.evaluations[0].state == "pending"


def test_precedence_cannot_be_repaired_by_later_events_and_end_waits_for_close():
    rules = (DeclareConstraint("precedence", "A", "B"), DeclareConstraint("end", "A"))
    result = check_declare(
        log_of("BA"),
        DeclareModel(("A", "B"), rules),
        DeclareConformanceSpec(observation="open"),
    )
    assert tuple(x.state for x in result.value.evaluations) == ("violated", "pending")
    assert result.value.violating_case_ids == ("c0",)


@pytest.mark.parametrize(
    "template,n,expected",
    [
        ("existence", 2, (False, False, True, True)),
        ("absence", 2, (True, True, False, False)),
        ("exactly", 2, (False, False, True, False)),
        ("exactly", 0, (True, False, False, False)),
        ("existence", 0, (True, True, True, True)),
        ("absence", 0, (False, False, False, False)),
    ],
)
def test_cardinality_thresholds(template, n, expected):
    model = DeclareModel(("A",), (DeclareConstraint(template, "A", cardinality=n),))
    result = check_declare(log_of("", "A", "AA", "AAA"), model)
    assert tuple(x.state == "satisfied" for x in result.value.evaluations) == expected


def test_discovery_counts_case_support_without_vacuous_inflation():
    result = discover_declare(
        log_of("AB", "A", "C", ""),
        DeclareDiscoverySpec(
            templates=("response",),
            activities=("A", "B"),
            min_support=0.5,
            min_confidence=0.5,
        ),
    )
    evidence = next(x for x in result.value.evidence if x.rule.source == "A")
    assert (
        evidence.activated_cases,
        evidence.satisfied_cases,
        evidence.vacuous_cases,
    ) == (2, 1, 2)
    assert evidence.support == 0.5
    assert evidence.confidence == 0.5
    stricter = discover_declare(
        log_of("AB", "A", "C", ""),
        DeclareDiscoverySpec(
            templates=("response",),
            activities=("A", "B"),
            min_support=0.5,
            min_confidence=0.5001,
        ),
    )
    assert DeclareConstraint("response", "A", "B") not in stricter.value.rules


def test_candidate_restriction_never_projects_intermediate_events():
    result = discover_declare(
        log_of("AXB"),
        DeclareDiscoverySpec(templates=("chain_response",), activities=("A", "B")),
    )
    assert DeclareConstraint("chain_response", "A", "B") not in result.value.rules


def test_requested_templates_have_no_hidden_dependency():
    absence = discover_declare(
        log_of("B"), DeclareDiscoverySpec(templates=("absence",), activities=("A",))
    )
    assert absence.value.rules == (DeclareConstraint("absence", "A"),)
    succession = discover_declare(
        log_of("AB"),
        DeclareDiscoverySpec(templates=("succession",), activities=("A", "B")),
    )
    assert DeclareConstraint("succession", "A", "B") in succession.value.rules


def test_no_discovery_from_empty_population_or_unactivated_candidates():
    empty = discover_declare(log_of())
    assert empty.status is ComputeStatus.UNAVAILABLE
    result = discover_declare(
        log_of("C"),
        DeclareDiscoverySpec(
            templates=("response",),
            activities=("A", "B"),
            min_support=0,
            min_confidence=0,
        ),
    )
    assert result.value.rules == ()


def test_negative_succession_is_prohibition_not_negation_of_positive():
    model = DeclareModel(
        ("A", "B"),
        tuple(
            DeclareConstraint(x, "A", "B")
            for x in ("succession", "nonsuccession", "nonchainsuccession")
        ),
    )
    result = check_declare(log_of("ABA"), model)
    assert tuple(x.state for x in result.value.evaluations) == (
        "violated",
        "violated",
        "violated",
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda: DeclareConstraint("unsupported", "A"),
        lambda: DeclareConstraint("response", "A", "A"),
        lambda: DeclareConstraint("response", "A"),
        lambda: DeclareConstraint("existence", "A", "B"),
        lambda: DeclareConstraint("init", "A", cardinality=2),
        lambda: DeclareConstraint("existence", "A", cardinality=True),
        lambda: DeclareDiscoverySpec(templates=("response", "response")),
        lambda: DeclareDiscoverySpec(min_confidence=float("nan")),
        lambda: DeclareConformanceSpec(observation="maybe"),
    ],
)
def test_declare_rejects_ambiguous_or_unsupported_contracts(make):
    with pytest.raises((ValueError, TypeError)):
        make()


def relation(model, kind, a, b):
    return next(
        (r for r in model.relations if (r.kind, r.source, r.target) == (kind, a, b)),
        None,
    )


def test_skeleton_discovery_uses_all_activations_not_trace_denominator():
    model = discover_log_skeleton(log_of("AAB")).value
    after = relation(model, "always_after", "A", "B")
    assert (after.fulfilled, after.eligible) == (2, 2)
    assert relation(model, "directly_follows", "A", "B") is None
    assert check_log_skeleton(log_of("AAB"), model).value.fit_case_count == 1


def test_skeleton_repeated_cooccurrence_never_creates_exclusion():
    model = discover_log_skeleton(
        log_of("AAAAAAAAAAB"), LogSkeletonSpec(noise_threshold=0.1)
    ).value
    assert relation(model, "never_together", "A", "B") is None


def test_skeleton_frequency_domains_use_case_population_and_deterministic_ties():
    model = discover_log_skeleton(
        log_of("AA", "AA", "AA", "A"), LogSkeletonSpec(noise_threshold=0.25)
    ).value
    assert model.activity_frequencies[0].allowed_counts == (2,)
    assert model.activity_frequencies[0].distribution == ((1, 1), (2, 3))
    assert check_log_skeleton(log_of("AA", "A"), model).value.fit_case_count == 1
    first = discover_log_skeleton(
        log_of("A", "AA"), LogSkeletonSpec(noise_threshold=0.5)
    ).value
    second = discover_log_skeleton(
        log_of("AA", "A"), LogSkeletonSpec(noise_threshold=0.5)
    ).value
    assert first.activity_frequencies == second.activity_frequencies
    assert first.activity_frequencies[0].allowed_counts == (1,)


@pytest.mark.parametrize("kind", ["always_after", "always_before", "directly_follows"])
def test_skeleton_conformance_rejects_single_matching_pair_with_later_violation(kind):
    sequence = "ABA" if kind != "always_before" else "BAB"
    a, b = ("A", "B") if kind != "always_before" else ("B", "A")
    model = LogSkeleton(
        ("A", "B"),
        (SkeletonRelation(kind, a, b),),
        (ActivityFrequency("A", (0, 1, 2)), ActivityFrequency("B", (0, 1, 2))),
    )
    evaluation = check_log_skeleton(log_of(sequence), model).value.traces[0]
    assert not evaluation.is_fit
    assert len(evaluation.deviations) == 1
    assert evaluation.deviations[0].kind == kind
    assert evaluation.fitness == pytest.approx(2 / 3)


def test_skeleton_empty_cases_zero_counts_unknown_activities():
    model = discover_log_skeleton(
        log_of("A", ""), LogSkeletonSpec(activities=("A", "B"))
    ).value
    assert tuple(x.allowed_counts for x in model.activity_frequencies) == ((0, 1), (0,))
    result = check_log_skeleton(log_of("", "C"), model).value
    assert result.traces[0].is_fit
    assert result.traces[1].deviations[0].kind == "unknown_activity"
    assert discover_log_skeleton(log_of()).status is ComputeStatus.UNAVAILABLE


def test_zero_noise_skeleton_accepts_every_training_trace_exhaustively():
    # This invariant catches contradictions between discovery and conformance.
    for length in range(5):
        for events in product("AB", repeat=length):
            log = log_of("".join(events), "AB", "")
            model = discover_log_skeleton(log).value
            assert check_log_skeleton(log, model).value.fit_case_count == 3, events


def test_skeleton_equivalence_checks_counts_not_only_coexistence():
    model = LogSkeleton(
        ("A", "B"),
        (SkeletonRelation("equivalence", "A", "B"),),
        (ActivityFrequency("A", (0, 1, 2)), ActivityFrequency("B", (0, 1, 2))),
    )
    result = check_log_skeleton(log_of("AB", "AAB", ""), model).value
    assert tuple(x.is_fit for x in result.traces) == (True, False, True)


def test_temporal_mean_and_population_vs_sample_variance():
    log = log_of("AB", "AB", times=((0, 2), (0, 4)))
    population = discover_temporal_profile(log).value.entries[0]
    sample = discover_temporal_profile(log, TemporalProfileSpec(ddof=1)).value.entries[
        0
    ]
    assert (population.count, population.mean, population.standard_deviation) == (
        2,
        3,
        1,
    )
    assert sample.standard_deviation == pytest.approx(sqrt(2))


def test_temporal_every_ordered_occurrence_and_relation_selection():
    log = log_of("AAB", times=((0, 1, 3),))
    profile = discover_temporal_profile(log).value
    ab = next(x for x in profile.entries if (x.source, x.target) == ("A", "B"))
    assert (ab.count, ab.mean, ab.standard_deviation) == (2, 2.5, 0.5)
    assert profile.observed_pairs == 3
    direct = discover_temporal_profile(
        log, TemporalProfileSpec(relation="directly_follows")
    ).value
    assert direct.observed_pairs == 2
    assert next(x for x in direct.entries if x.target == "B").mean == 2


def test_temporal_singleton_variance_zero_or_unknown_depends_on_ddof():
    log = log_of("AB", times=((0, 3),))
    population = discover_temporal_profile(log).value
    sample = discover_temporal_profile(log, TemporalProfileSpec(ddof=1)).value
    assert population.entries[0].standard_deviation == 0
    assert sample.entries[0].standard_deviation is None
    result = check_temporal_profile(log, sample)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.observations[0].reason == "unknown_variance"


def test_temporal_bounds_are_inclusive_and_zero_variance_mismatch_explicit():
    model = discover_temporal_profile(log_of("AB", "AB", times=((0, 2), (0, 4)))).value
    result = check_temporal_profile(
        log_of("AB", "AB", "AB", times=((0, 2), (0, 4), (0, 4.001))),
        model,
        TemporalConformanceSpec(zeta=1),
    )
    assert tuple(x.state for x in result.value.observations) == (
        "satisfied",
        "satisfied",
        "violated",
    )
    zero = discover_temporal_profile(log_of("AB", times=((0, 3),))).value
    result = check_temporal_profile(log_of("AB", "AB", times=((0, 3), (0, 4))), zero)
    assert result.value.observations[0].z_score == 0
    assert result.value.observations[1].z_score is None
    assert result.value.observations[1].reason == "zero_variance_mismatch"
    assert result.value.violated_pairs == 1


def test_temporal_missing_and_reversed_times_have_explicit_coverage():
    log = log_of("AB", "AB", "AB", times=((0, 2), (10, 5), (0, None)))
    result = discover_temporal_profile(log)
    assert result.status is ComputeStatus.PARTIAL
    assert (
        result.value.observed_pairs,
        result.value.excluded_negative,
        result.value.excluded_missing,
    ) == (3, 1, 1)
    assert result.value.entries[0].count == 1
    reject = discover_temporal_profile(
        log, TemporalProfileSpec(missing_timestamps="reject")
    )
    assert reject.status is ComputeStatus.UNAVAILABLE
    included = discover_temporal_profile(
        log_of("AB", times=((10, 5),)),
        TemporalProfileSpec(negative_durations="include"),
    )
    assert included.value.entries[0].mean == -5
    assert included.value.entries[0].source == "A"  # never silently reorders


def test_temporal_conformance_reports_unprofiled_pairs_without_normal_credit():
    model = discover_temporal_profile(log_of("AB")).value
    result = check_temporal_profile(log_of("AC"), model)
    assert result.status is ComputeStatus.PARTIAL
    assert (result.value.satisfied_pairs, result.value.unknown_pairs) == (0, 1)
    ignored = check_temporal_profile(
        log_of("AC"), model, TemporalConformanceSpec(unknown_pairs="ignore")
    )
    assert ignored.status is ComputeStatus.COMPUTED
    assert (ignored.value.satisfied_pairs, ignored.value.ignored_pairs) == (0, 1)


def test_temporal_interval_start_key_and_unit_conversion():
    log = log_of("AB", times=((60, 240),), starts=((0, 180),))
    point = discover_temporal_profile(
        log, TemporalProfileSpec(time_unit="minutes")
    ).value
    interval = discover_temporal_profile(
        log, TemporalProfileSpec(time_unit="minutes", start_timestamp_key="start")
    ).value
    assert point.entries[0].mean == 3
    assert interval.entries[0].mean == 2


def test_temporal_timezone_conversion_uses_absolute_time():
    local = timezone(timedelta(hours=9))
    t1 = datetime(2026, 1, 1, 9, tzinfo=local)
    t2 = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    model = discover_temporal_profile(log_of("AB", times=((t1, t2),))).value
    assert model.entries[0].mean == 10


def test_temporal_naive_time_is_unknown_not_imputed():
    naive = datetime(2026, 1, 1)
    result = discover_temporal_profile(log_of("AB", times=((naive, 2),)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert any(x.code == "missing_timestamp_pairs" for x in result.issues)


def test_temporal_empty_population_never_creates_zero_mean():
    assert (
        discover_temporal_profile(log_of("", "A")).status is ComputeStatus.UNAVAILABLE
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda: TemporalProfileSpec(ddof=2),
        lambda: TemporalProfileSpec(ddof=True),
        lambda: TemporalProfileSpec(time_unit="business_days"),
        lambda: TemporalProfileSpec(negative_durations="sort"),
        lambda: TemporalConformanceSpec(zeta=float("inf")),
        lambda: TemporalConformanceSpec(zeta=-1),
        lambda: TemporalConformanceSpec(unknown_pairs="normal"),
        lambda: TemporalProfileEntry("A", "B", 0, 0, 0),
        lambda: TemporalProfileEntry("A", "B", 1, 0, -1),
    ],
)
def test_temporal_validation(make):
    with pytest.raises((ValueError, TypeError)):
        make()


def test_temporal_overflow_score_is_not_a_nonfinite_serialized_number():
    model = TemporalProfile(
        (TemporalProfileEntry("A", "B", 2, 0, 1e-320),), TemporalProfileSpec(), 1, 2
    )
    result = check_temporal_profile(log_of("AB"), model)
    assert result.value.observations[0].state == "violated"
    assert result.value.observations[0].reason == "standardized_distance_overflow"
    assert result.value.observations[0].z_score is None


def footprint(*, parallel=False, loops=()):
    return FootprintReference(
        ("A", "B"),
        () if parallel else (("A", "B"),),
        (("A", "B"), ("B", "A")) if parallel else (),
        loops,
        ("A",),
        ("B",),
        2,
    )


def test_footprint_parallel_model_accepts_causal_observation_with_explicit_precision():
    result = check_footprints(log_of("AB"), footprint(parallel=True)).value
    assert result.is_fit
    assert result.relation_fitness == 1
    assert result.relation_precision == 0.5


def test_footprint_observed_reverse_relation_violates_causal_model():
    result = check_footprints(
        log_of("ABA"), footprint(), FootprintConformanceSpec(check_boundaries=False)
    ).value
    assert not result.is_fit
    assert result.violations == (type(result.violations[0])("relation", "B", "A"),)
    assert result.relation_fitness == 0.5
    assert result.relation_precision == 1


def test_footprint_loop_boundaries_unknown_and_empty_denominators():
    result = check_footprints(log_of("AAB"), footprint(loops=("A",))).value
    assert result.is_fit
    assert result.relation_fitness == result.relation_precision == 1
    bad = check_footprints(log_of("B", "AC"), footprint()).value
    assert {x.kind for x in bad.violations} == {
        "start_activity",
        "minimum_trace_length",
        "unknown_activity",
        "relation",
        "end_activity",
    }
    empty = check_footprints(
        log_of(""), FootprintReference((), (), (), (), (), (), 0)
    ).value
    assert empty.is_fit
    assert empty.relation_fitness is None and empty.relation_precision is None


def test_new_result_identity_includes_rule_model_and_semantic_options():
    log = log_of("AB")
    response = DeclareModel(("A", "B"), (DeclareConstraint("response", "A", "B"),))
    precedence = DeclareModel(("A", "B"), (DeclareConstraint("precedence", "A", "B"),))
    first = check_declare(log, response)
    assert first.computation_id == check_declare(log, response).computation_id
    assert first.computation_id != check_declare(log, precedence).computation_id
    assert (
        first.computation_id
        != check_declare(
            log, response, DeclareConformanceSpec(observation="open")
        ).computation_id
    )
    assert first.parent_computation_ids


def test_case_mapping_failure_is_unavailable_not_empty_success():
    log = CaseLog((CaseTrace("c", (CaseEvent("e"),)),))
    result = discover_declare(log)
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert result.issues[0].code == "case_traces_unavailable"


def test_budgets_stop_before_inferring_a_truncated_model_or_population():
    declare = discover_declare(
        log_of("ABC"), DeclareDiscoverySpec(max_candidate_rules=1)
    )
    skeleton = discover_log_skeleton(
        log_of("ABC"), LogSkeletonSpec(max_relation_candidates=1)
    )
    temporal = discover_temporal_profile(
        log_of("ABC"), TemporalProfileSpec(max_observations=2)
    )
    for result, code in (
        (declare, "candidate_rule_limit"),
        (skeleton, "candidate_relation_limit"),
        (temporal, "temporal_pair_limit"),
    ):
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
        assert result.issues[0].code == code
    model = discover_temporal_profile(
        log_of("AB"), TemporalProfileSpec(max_observations=2)
    ).value
    limited = check_temporal_profile(log_of("ABC"), model)
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.issues[0].code == "temporal_pair_limit"


def test_discovered_footprint_model_interoperates_without_dictionary_coercion():
    from pix.case_centric.discovery import discover_footprints

    log = log_of("AB", "AAB")
    model = discover_footprints(log).value
    result = check_footprints(log, model)
    assert result.value.is_fit
    assert result.value.relation_fitness == 1
    assert result.value.relation_precision == 1


def test_all_seven_operator_results_roundtrip_including_integer_options():
    from pix.results import result_from_json, result_json_bytes

    log = log_of("AB", "AAB")
    declare = discover_declare(
        log, DeclareDiscoverySpec(min_support=0, min_confidence=0)
    )
    skeleton = discover_log_skeleton(log, LogSkeletonSpec(noise_threshold=0))
    temporal = discover_temporal_profile(log)
    results = (
        declare,
        check_declare(log, declare.value),
        skeleton,
        check_log_skeleton(log, skeleton.value),
        temporal,
        check_temporal_profile(log, temporal.value, TemporalConformanceSpec(zeta=1)),
        check_footprints(log, footprint(loops=("A",))),
        discover_temporal_profile(log_of("AB", "AB", times=((0, 1), (0, None)))),
        discover_declare(log_of()),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result, result.operator_id
    # Public, manually supplied model fields also normalize legitimate integers.
    manual = TemporalProfile(
        (TemporalProfileEntry("A", "B", 2, 0, 0),), TemporalProfileSpec(), 1, 2
    )
    result = check_temporal_profile(
        log_of("AB"), manual, TemporalConformanceSpec(zeta=0)
    )
    assert result_from_json(result_json_bytes(result)) == result


def test_duplicate_skeleton_constraints_cannot_reweight_fitness():
    with pytest.raises(ValueError, match="duplicate semantic"):
        LogSkeleton(
            ("A", "B"),
            (
                SkeletonRelation("always_after", "A", "B"),
                SkeletonRelation("always_after", "A", "B", 1, 1),
            ),
            (ActivityFrequency("A", (0, 1, 2)), ActivityFrequency("B", (0, 1, 2))),
        )
    with pytest.raises(ValueError, match="duplicate semantic"):
        LogSkeleton(
            ("A", "B"),
            (
                SkeletonRelation("equivalence", "A", "B"),
                SkeletonRelation("equivalence", "B", "A"),
            ),
            (ActivityFrequency("A", (0, 1, 2)), ActivityFrequency("B", (0, 1, 2))),
        )


def test_negative_declare_preserves_each_activation_with_linear_witness_output():
    model = DeclareModel(("A", "B"), (DeclareConstraint("noncoexistence", "A", "B"),))
    result = check_declare(log_of("A" * 100 + "B" * 100), model)
    obligations = result.value.evaluations[0].obligations
    assert len(obligations) == 200
    assert sum(len(x.witness_indices) for x in obligations) == 200
    assert all(x.state == "violated" for x in obligations)
    limited = check_declare(
        log_of("A" * 100 + "B" * 100),
        model,
        DeclareConformanceSpec(max_obligations=199),
    )
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.issues[0].code == "declare_obligation_limit"


@pytest.mark.parametrize(
    "make",
    [
        lambda: DeclareModel(("A",), (), case_count=-1),
        lambda: DeclareModel(("A",), (), evidence=("bad",)),
        lambda: SkeletonRelation("always_after", "A", "B", 2, 1),
        lambda: ActivityFrequency("A", (1,), ((1, -1),)),
        lambda: ActivityFrequency("A", (1,), ((0, 2),)),
        lambda: TemporalProfile(
            (TemporalProfileEntry("A", "B", 1, 1, 0),), TemporalProfileSpec(), 1, 2
        ),
        lambda: TemporalProfile(
            (TemporalProfileEntry("A", "B", 1, 1, 1),), TemporalProfileSpec(), 1, 1
        ),
    ],
)
def test_public_model_provenance_rejects_malformed_or_inconsistent_counts(make):
    with pytest.raises((ValueError, TypeError)):
        make()


def test_model_footprint_converter_preserves_epsilon_minimum_and_parent_evidence():
    from pix.case_centric.model_discovery import discover_model_footprints
    from pix.contracts.discovery import ProcessTree
    from pix.results import result_from_json, result_json_bytes

    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    discovered = discover_model_footprints(tree)
    reference = footprint_reference(discovered)
    assert reference.source_profile == "model-reachable"
    assert reference.reference_computation_id == discovered.computation_id
    assert reference.minimum_trace_length == 2
    assert reference.accepts_empty_trace is False
    assert reference.required_activities == ("A", "B")
    result = check_footprints(log_of("AB"), discovered)
    assert result.value.is_fit
    assert discovered.computation_id in result.parent_computation_ids
    assert len(result.parent_computation_ids) == 2
    assert result_from_json(result_json_bytes(result)) == result
    rejected = check_footprints(
        log_of(""), discovered, FootprintConformanceSpec(check_minimum_length=False)
    )
    assert not rejected.value.is_fit
    assert "empty_trace_not_accepted" in {x.kind for x in rejected.value.violations}


def test_model_footprint_converter_accepts_tau_but_rejects_no_accepting_language():
    from pix.case_centric.model_discovery import discover_model_footprints
    from pix.contracts.discovery import ProcessTree
    from pix.contracts.models import Marking, PetriNet, Place

    tau = discover_model_footprints(ProcessTree("tau"))
    assert footprint_reference(tau).accepts_empty_trace is True
    assert check_footprints(log_of(""), tau).value.is_fit
    dead = PetriNet(
        (Place("p"), Place("q")), (), (), Marking((("p", 1),)), Marking((("q", 1),))
    )
    discovered = discover_model_footprints(dead)
    assert discovered.value.complete
    assert footprint_reference(discovered).accepted_language_exists is False
    result = check_footprints(log_of("", "A"), discovered)
    assert not result.value.is_fit
    assert {
        x.case_id for x in result.value.violations if x.kind == "no_accepting_behavior"
    } == {"c0", "c1"}


def test_model_footprint_converter_rejects_partial_negative_facts_and_unproven_minimum():
    from dataclasses import replace

    from pix.case_centric.model_discovery import (
        ModelFootprintSpec,
        discover_model_footprints,
    )
    from pix.contracts.discovery import ProcessTree

    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    partial = discover_model_footprints(tree, ModelFootprintSpec(max_states=1))
    assert partial.status is ComputeStatus.PARTIAL
    with pytest.raises(ValueError, match="complete computed"):
        footprint_reference(partial)
    with pytest.raises(ValueError, match="partial model footprints"):
        footprint_reference(partial.value)
    full = discover_model_footprints(tree).value
    unknown_minimum = replace(
        full, minimum_trace_length=999, minimum_length_proven=False
    )
    assert footprint_reference(unknown_minimum).minimum_trace_length is None


def test_log_footprint_parent_identity_and_empty_observed_language_are_explicit():
    from pix.case_centric.discovery import discover_footprints

    result = discover_footprints(log_of("AB"))
    reference = footprint_reference(result)
    assert reference.source_profile == "observed-case-footprints"
    assert reference.reference_computation_id == result.computation_id
    checked = check_footprints(log_of("AB"), result)
    assert result.computation_id in checked.parent_computation_ids
    empty = discover_footprints(log_of())
    assert footprint_reference(empty).accepted_language_exists is False
    assert not check_footprints(log_of(""), empty).value.is_fit
