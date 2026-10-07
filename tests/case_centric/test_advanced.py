"""Independent finite oracles for native case-centric advanced profiles."""

from dataclasses import replace
from fractions import Fraction
from itertools import permutations, product

import pytest

from pix.case_centric.advanced import (
    BoseDriftSpec,
    CaseAttributeClusteringSpec,
    CaseClusteringSpec,
    CaseProfileClusteringSpec,
    CaseRetrievalSpec,
    CaseVector,
    DecisionExample,
    DecisionTreeSpec,
    LanguageDistanceSpec,
    LanguageEntry,
    RationalValue,
    StochasticLanguage,
    cluster_case_attribute_groups,
    cluster_case_profiles,
    cluster_cases,
    compare_stochastic_languages,
    detect_bose_drift,
    mine_decision_tree,
    predict_decision_tree,
    retrieve_similar_cases,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log(*words, ids=None):
    ids = ids or tuple(f"c{i}" for i in range(len(words)))
    return CaseLog(
        tuple(
            CaseTrace(
                case_id,
                tuple(
                    CaseEvent(
                        f"{case_id}:e{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for case_id, word in zip(ids, words)
        )
    )


def language(entries):
    return StochasticLanguage(
        tuple(
            LanguageEntry(
                tuple(word),
                RationalValue(Fraction(mass).numerator, Fraction(mass).denominator),
            )
            for word, mass in entries
        )
    )


def value(result):
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


def test_clustering_exact_partition_and_case_permutation():
    first = log("AB", "AB", "CD", "CD")
    expected = (("c0", "c1"), ("c2", "c3"))
    assert value(cluster_cases(first)).clusters == expected
    permuted = CaseLog(tuple(reversed(first.traces)))
    assert value(cluster_cases(permuted)).clusters == expected


@pytest.mark.parametrize(
    "linkage, final_distance", [("single", 3.0), ("complete", 5.0), ("average", 4.0)]
)
def test_vector_clustering_linkage_has_independent_known_height(
    linkage, final_distance
):
    result = value(
        cluster_cases(
            log("A", "B", "C"),
            CaseClusteringSpec(1, "euclidean", linkage),
            vectors=(
                CaseVector("c0", (0.0,)),
                CaseVector("c1", (2.0,)),
                CaseVector("c2", (5.0,)),
            ),
        )
    )
    assert result.merges[0].distance == 2.0
    assert result.merges[-1].distance == final_distance


def test_vector_identity_changes_even_when_partition_does_not():
    spec = CaseClusteringSpec(1, "euclidean")
    first = cluster_cases(
        log("A", "B"),
        spec,
        vectors=(CaseVector("c0", (0.0,)), CaseVector("c1", (1.0,))),
    )
    second = cluster_cases(
        log("A", "B"),
        spec,
        vectors=(CaseVector("c0", (0.0,)), CaseVector("c1", (2.0,))),
    )
    assert first.computation_id != second.computation_id
    assert first.value.clusters == second.value.clusters


def test_clustering_dfg_explicitly_loses_singleton_activity_information():
    result = value(
        cluster_cases(log("A", "B", "AB"), CaseClusteringSpec(2, "dfg_cosine"))
    )
    assert result.clusters == (("c0", "c1"), ("c2",))
    assert result.pair_distances[0] == ("c0", "c1", 0.0)


def test_clustering_budget_does_not_claim_partition():
    result = cluster_cases(log("ABC", "ABD"), CaseClusteringSpec(1, max_edit_cells=1))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "clustering_resource_limit"


def test_clustering_vector_schema_errors_and_empty_population():
    with pytest.raises(ValueError, match="every selected case"):
        cluster_cases(
            log("A", "B"),
            CaseClusteringSpec(1, "euclidean"),
            vectors=(CaseVector("c0", (1.0,)),),
        )
    with pytest.raises(ValueError, match="equal dimensions"):
        cluster_cases(
            log("A", "B"),
            CaseClusteringSpec(1, "euclidean"),
            vectors=(CaseVector("c0", (1.0,)), CaseVector("c1", ())),
        )
    assert cluster_cases(log()).status is ComputeStatus.UNAVAILABLE


def test_attribute_groups_are_sublog_leaves_not_individual_trace_leaves():
    dataset = log("AB", "AB", "AB", "ZZ")
    dataset = CaseLog(
        tuple(
            replace(trace, attributes=(CaseAttribute("department", "string", group),))
            for trace, group in zip(
                dataset.traces, ("first", "first", "second", "third")
            )
        )
    )
    result = value(
        cluster_case_attribute_groups(
            dataset, CaseAttributeClusteringSpec("department")
        )
    )
    assert result.case_clusters == (("c0", "c1", "c2"), ("c3",))
    assert result.merges[0].distance == 0.0
    assert len(result.groups) == 3


def test_attribute_group_mean_keeps_case_multiplicity_and_typed_values():
    dataset = log("A", "A", "B", "B")
    dataset = CaseLog(
        tuple(
            replace(
                trace,
                attributes=(
                    CaseAttribute(
                        "group", "int" if i < 3 else "string", 1 if i < 3 else "1"
                    ),
                ),
            )
            for i, trace in enumerate(dataset.traces)
        )
    )
    result = value(
        cluster_case_attribute_groups(
            dataset,
            CaseAttributeClusteringSpec("group", cluster_count=1, distance="mean_edit"),
        )
    )
    assert len(result.groups) == 2
    assert result.group_distances[0][2] == pytest.approx(2 / 3)


def test_attribute_group_dfg_does_not_create_cross_case_edges():
    dataset = log("A", "B", "AB")
    dataset = CaseLog(
        tuple(
            replace(
                trace,
                attributes=(CaseAttribute("group", "string", "x" if i < 2 else "y"),),
            )
            for i, trace in enumerate(dataset.traces)
        )
    )
    result = value(
        cluster_case_attribute_groups(
            dataset,
            CaseAttributeClusteringSpec(
                "group", cluster_count=1, distance="dfg_cosine"
            ),
        )
    )
    assert result.group_distances[0][2] == 1.0


def test_profile_kmeans_has_exact_known_centroids_and_inertia():
    spec = CaseProfileClusteringSpec(include_dfg=False)
    dataset = log("", "AA", "A" * 10, "A" * 12)
    result = value(cluster_case_profiles(dataset, spec))
    assert tuple(cluster.case_ids for cluster in result.clusters) == (
        ("c0", "c1"),
        ("c2", "c3"),
    )
    assert tuple(cluster.centroid[0].as_fraction() for cluster in result.clusters) == (
        1,
        11,
    )
    assert result.inertia.as_fraction() == 4
    assert result.converged
    permuted = value(
        cluster_case_profiles(CaseLog(tuple(reversed(dataset.traces))), spec)
    )
    assert permuted == result


def test_profile_kmeans_feature_families_and_no_cross_case_edges():
    result = value(
        cluster_case_profiles(
            log("A", "B", "AB"), CaseProfileClusteringSpec(cluster_count=1)
        )
    )
    assert tuple(
        (column.kind, column.activity, column.target) for column in result.columns
    ) == (
        ("activity", "A", None),
        ("activity", "B", None),
        ("directly_follows", "A", "B"),
    )
    assert tuple(value.as_fraction() for value in result.clusters[0].centroid) == (
        Fraction(2, 3),
        Fraction(2, 3),
        Fraction(1, 3),
    )


def test_profile_kmeans_budgets_never_claim_convergence():
    dataset = log("", "AA", "A" * 10, "A" * 12)
    result = cluster_case_profiles(
        dataset, CaseProfileClusteringSpec(include_dfg=False, max_iterations=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert not result.value.converged
    assert result.value.inertia.as_fraction() == 4
    assert (
        cluster_case_profiles(
            dataset, CaseProfileClusteringSpec(max_distance_evaluations=1)
        ).status
        is ComputeStatus.UNAVAILABLE
    )
    assert (
        cluster_case_profiles(log("A", "A"), CaseProfileClusteringSpec()).status
        is ComputeStatus.UNAVAILABLE
    )


def test_retrieval_preserves_ties_and_reference_identity():
    query, reference = log("AB", ids=("q",)), log("AB", "AB", "ZZ", ids=("x", "y", "z"))
    result = retrieve_similar_cases(query, reference)
    assert [item.case_id for item in value(result).queries[0].neighbors] == ["x", "y"]
    assert len(result.parent_computation_ids) == 2
    strict = value(
        retrieve_similar_cases(
            query, reference, CaseRetrievalSpec(include_boundary_ties=False)
        )
    )
    assert [item.case_id for item in strict.queries[0].neighbors] == ["x"]
    assert retrieve_similar_cases(query, log()).status is ComputeStatus.UNAVAILABLE


def test_transport_known_rational_optimum_and_marginals():
    first = language([("A", Fraction(1, 2)), ("B", Fraction(1, 2))])
    second = language([("A", Fraction(9, 10)), ("B", Fraction(1, 10))])
    result = value(compare_stochastic_languages(first, second))
    assert result.distance.as_fraction() == Fraction(2, 5)
    assert result.transported_mass.as_fraction() == 1
    outgoing, incoming = {}, {}
    for flow in result.flows:
        outgoing[flow.source] = outgoing.get(flow.source, 0) + flow.mass.as_fraction()
        incoming[flow.target] = incoming.get(flow.target, 0) + flow.mass.as_fraction()
    assert outgoing == {("A",): Fraction(1, 2), ("B",): Fraction(1, 2)}
    assert incoming == {("A",): Fraction(9, 10), ("B",): Fraction(1, 10)}


def test_transport_normalized_edit_and_empty_word():
    assert value(
        compare_stochastic_languages(language([("AB", 1)]), language([("AC", 1)]))
    ).distance.as_fraction() == Fraction(1, 2)
    assert (
        value(
            compare_stochastic_languages(language([("", 1)]), language([("", 1)]))
        ).distance.as_fraction()
        == 0
    )
    assert (
        value(
            compare_stochastic_languages(language([("", 1)]), language([("AB", 1)]))
        ).distance.as_fraction()
        == 1
    )
    assert (
        value(
            compare_stochastic_languages(
                language([("AB", 1)]),
                language([("AC", 1)]),
                LanguageDistanceSpec(normalized_edit=False),
            )
        ).distance.as_fraction()
        == 1
    )


def oracle_edit(left, right):
    # Recursive exhaustive edit decomposition, independently of production DP.
    if not left:
        return len(right)
    if not right:
        return len(left)
    return min(
        1 + oracle_edit(left[1:], right),
        1 + oracle_edit(left, right[1:]),
        (left[0] != right[0]) + oracle_edit(left[1:], right[1:]),
    )


@pytest.mark.parametrize(
    "words_left, words_right",
    [
        (("A", "B", "AB"), ("AB", "A", "BA")),
        (("", "AB", "BA"), ("B", "A", "BB")),
        (("A", "AB", "AA"), ("B", "BA", "BB")),
    ],
)
def test_transport_matches_exhaustive_assignment_oracle(words_left, words_right):
    # Equal unit masses: Birkhoff extreme points are permutations. Enumerating
    # all assignments supplies an independent finite optimal transport oracle.
    expected = min(
        sum(
            (
                Fraction(oracle_edit(a, b), max(len(a), len(b), 1))
                for a, b in zip(words_left, ordering)
            ),
            Fraction(),
        )
        / 3
        for ordering in permutations(words_right)
    )
    first, second = (
        language([(word, 1) for word in words_left]),
        language([(word, 1) for word in words_right]),
    )
    actual = value(compare_stochastic_languages(first, second))
    assert actual.distance.as_fraction() == expected
    assert (
        value(compare_stochastic_languages(second, first)).distance == actual.distance
    )


def test_transport_mass_normalization_duplication_and_probability_validation():
    first = language([("A", 1), ("A", 1), ("B", 2)])
    second = language([("A", 500), ("B", 500)])
    assert value(compare_stochastic_languages(first, second)).distance.numerator == 0
    with pytest.raises(ValueError, match="sum exactly to one"):
        compare_stochastic_languages(
            first, second, LanguageDistanceSpec(normalize_mass=False)
        )
    assert (
        compare_stochastic_languages(language([]), second).status
        is ComputeStatus.UNAVAILABLE
    )
    with pytest.raises(ValueError):
        language([("A", -1)])


def test_transport_limit_returns_witness_without_false_emd():
    result = compare_stochastic_languages(
        language([("A", 1), ("B", 1)]),
        language([("A", 1), ("B", 1)]),
        LanguageDistanceSpec(max_augmentations=1),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.distance is None
    assert result.value.transported_mass.as_fraction() == Fraction(1, 2)
    assert result.value.status == "resource_limit"


def test_transport_case_log_uses_trace_multiplicity():
    result = compare_stochastic_languages(log("A", "A", "B"), log("A", "B", "B"))
    assert value(result).distance.as_fraction() == Fraction(1, 3)
    assert len(result.parent_computation_ids) == 2


def test_transport_requires_residual_rerouting_instead_of_greedy_matching():
    # Greedily allocating A->AB first gives 1/2. A residual reroute to A->AAA
    # and B->AB attains the independently enumerated optimum 7/18.
    first, second = (
        language([("", 1), ("A", 1), ("B", 1)]),
        language([("", 1), ("AB", 1), ("AAA", 1)]),
    )
    result = value(compare_stochastic_languages(first, second))
    assert result.distance.as_fraction() == Fraction(7, 18)


def xor_examples():
    return tuple(
        DecisionExample(f"c{i}", (float(a), float(b)), "true" if a != b else "false")
        for i, (a, b) in enumerate(product((0, 1), repeat=2))
    )


def test_decision_xor_requires_zero_gain_root_then_exact_guards():
    examples = xor_examples()
    result = value(
        mine_decision_tree(
            log("A", "B", "C", "D"), examples, DecisionTreeSpec(("x", "y"), max_depth=2)
        )
    )
    assert result.training_correct == result.training_count == 4
    assert len(result.guards) == 4
    predictions = predict_decision_tree(
        result, tuple(CaseVector(item.case_id, item.features) for item in examples)
    )
    assert tuple(item.prediction for item in predictions) == tuple(
        item.target for item in examples
    )
    # Every observed point satisfies exactly one conjunction guard.
    for example in examples:
        guards = [
            guard
            for guard in result.guards
            if all(
                example.features[condition.feature_index] <= condition.threshold
                if condition.operator == "<="
                else example.features[condition.feature_index] > condition.threshold
                for condition in guard.conditions
            )
        ]
        assert len(guards) == 1
        assert guards[0].prediction == example.target


def test_decision_depth_stop_training_only_identity_and_permutation():
    dataset = log("A", "B", "C", "D", "H")
    examples = xor_examples()
    first = mine_decision_tree(
        dataset, examples, DecisionTreeSpec(("x", "y"), max_depth=0)
    )
    assert value(first).training_correct == 2
    assert first.value.nodes[0].stop_reason == "max_depth"
    assert "c4" not in first.value.training_case_ids
    snapshot = first.value
    predict_decision_tree(snapshot, (CaseVector("holdout", (500.0, -100.0)),))
    assert first.value == snapshot
    permuted = mine_decision_tree(
        dataset, tuple(reversed(examples)), DecisionTreeSpec(("x", "y"), max_depth=0)
    )
    assert permuted.computation_id == first.computation_id
    assert permuted.value == first.value
    changed = mine_decision_tree(
        dataset,
        (DecisionExample("c0", (0.0, 0.0), "changed"),) + examples[1:],
        DecisionTreeSpec(("x", "y"), max_depth=0),
    )
    assert changed.value.training_digest != first.value.training_digest


def test_decision_split_budget_stays_valid_partial_model():
    result = mine_decision_tree(
        log("A", "B", "C", "D"),
        xor_examples(),
        DecisionTreeSpec(("x", "y"), max_split_evaluations=1),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.status == "resource_limit"
    assert result.value.nodes[0].stop_reason == "resource_limit"
    assert result.value.training_correct == 2


def test_decision_rejects_foreign_cases_and_nonfinite_data():
    with pytest.raises(ValueError, match="outside"):
        mine_decision_tree(
            log("A"),
            (DecisionExample("foreign", (0.0,), "x"),),
            DecisionTreeSpec(("x",)),
        )
    with pytest.raises(ValueError, match="finite"):
        DecisionExample("x", (float("nan"),), "yes")


def test_decision_integer_threshold_does_not_round_above_float_precision():
    examples = (
        DecisionExample("c0", (2**53 + 1,), "left"),
        DecisionExample("c1", (2**53 + 2,), "right"),
    )
    model = value(
        mine_decision_tree(
            log("A", "B"), examples, DecisionTreeSpec(("x",), max_depth=1)
        )
    )
    assert model.nodes[0].threshold == 2**53 + 1
    predictions = predict_decision_tree(
        model, tuple(CaseVector(item.case_id, item.features) for item in examples)
    )
    assert tuple(item.prediction for item in predictions) == ("left", "right")
    assert model.training_correct == 2


def test_decision_rejects_malformed_cyclic_model_on_prediction():
    examples = (
        DecisionExample("c0", (0,), "left"),
        DecisionExample("c1", (1,), "right"),
    )
    model = value(mine_decision_tree(log("A", "B"), examples, DecisionTreeSpec(("x",))))
    with pytest.raises(ValueError, match="cycle|conserve"):
        replace(model, nodes=(replace(model.nodes[0], left=0),) + model.nodes[1:])


def test_bose_relation_counts_and_exact_permutation_known_p():
    result = value(
        detect_bose_drift(
            log("AB", "AB", "BA", "BA"),
            BoseDriftSpec(sublog_size=1, window_size=2, threshold=0.4),
        )
    )
    assert result.sublogs[0].feature_values == (0, 0, 2, 1, 0, 1)
    assert result.sublogs[-1].feature_values == (1, 0, 1, 0, 0, 2)
    assert len(result.windows) == 1
    assert result.windows[0].p_value.as_fraction() == Fraction(1, 3)
    assert result.windows[0].squared_mean_distance.as_fraction() == 4
    assert result.selected_boundaries == (2,)
    assert result.windows[0].boundary_case_id == "c2"
    assert result.windows[0].permutations_evaluated == 6


def test_bose_mixed_eventually_follows_and_repeated_activity():
    result = value(
        detect_bose_drift(
            log("AB", "BA", "AB", "BA"), BoseDriftSpec(sublog_size=2, window_size=1)
        )
    )
    assert result.sublogs[0].feature_values == (0, 1, 1, 0, 1, 1)
    assert result.windows[0].p_value.as_fraction() == 1
    repeated = value(
        detect_bose_drift(log("AA", "AA"), BoseDriftSpec(sublog_size=1, window_size=1))
    )
    assert repeated.sublogs[0].feature_values == (1, 0, 0)


def test_bose_rc_collision_is_visible_not_a_false_zero_difference_claim():
    # Different eventually-follows graphs collapse into identical RC counts.
    result = value(
        detect_bose_drift(log("AB", "CB"), BoseDriftSpec(sublog_size=1, window_size=1))
    )
    assert result.sublogs[0].feature_values == result.sublogs[1].feature_values
    assert result.sublogs[0].feature_values == (0, 0, 3, 1, 0, 2, 0, 0, 3)
    assert result.windows[0].p_value.as_fraction() == 1
    assert result.selected_boundaries == ()


def test_bose_seeded_monte_carlo_does_not_claim_exact_test():
    spec = BoseDriftSpec(
        sublog_size=1,
        window_size=2,
        permutation_mode="monte_carlo",
        permutations=17,
        seed=23,
    )
    first = detect_bose_drift(log("AB", "AB", "BA", "BA"), spec)
    second = detect_bose_drift(log("AB", "AB", "BA", "BA"), spec)
    assert value(first) == value(second)
    assert first.computation_id == second.computation_id
    assert first.value.windows[0].permutations_evaluated == 17
    assert first.value.windows[0].p_value.as_fraction() > 0


def test_bose_resource_limit_insufficient_windows_and_omitted_cases():
    assert (
        detect_bose_drift(log("A"), BoseDriftSpec(sublog_size=1, window_size=1)).status
        is ComputeStatus.UNAVAILABLE
    )
    result = detect_bose_drift(
        log("AB", "AB", "BA", "BA"),
        BoseDriftSpec(sublog_size=1, window_size=2, max_permutation_evaluations=5),
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    leftover = value(
        detect_bose_drift(
            log("A", "A", "B", "B", "C"),
            BoseDriftSpec(sublog_size=2, window_size=1, keep_leftover=False),
        )
    )
    assert leftover.omitted_case_ids == ("c4",)


def test_incomplete_projection_is_not_silently_trained_or_clustered():
    invalid = CaseLog((CaseTrace("bad", (CaseEvent("e"),)),))
    assert cluster_cases(invalid).status is ComputeStatus.INVALID_INPUT
    assert detect_bose_drift(invalid).status is ComputeStatus.INVALID_INPUT
    assert (
        compare_stochastic_languages(invalid, log("A")).status
        is ComputeStatus.INVALID_INPUT
    )


def test_failed_multi_input_requests_retain_both_operand_identities():
    invalid = CaseLog((CaseTrace("bad", (CaseEvent("e"),)),))
    first = retrieve_similar_cases(log("A"), invalid)
    second = retrieve_similar_cases(log("B"), invalid)
    assert first.status is ComputeStatus.INVALID_INPUT
    assert first.computation_id != second.computation_id
    assert len(first.parent_computation_ids) == 2
    assert (
        compare_stochastic_languages(log("A"), invalid).computation_id
        != compare_stochastic_languages(log("B"), invalid).computation_id
    )


def test_specs_reject_bool_limits_and_unrecognized_modes():
    with pytest.raises(ValueError):
        CaseClusteringSpec(cluster_count=True)
    with pytest.raises(ValueError):
        BoseDriftSpec(permutation_mode="imaginary")
    with pytest.raises(ValueError):
        DecisionTreeSpec(("x", "x"))
    with pytest.raises(ValueError):
        RationalValue(1, 0)


def test_public_result_roundtrip_all_advanced_schemas_and_statuses():
    from pix.results import result_from_json, result_json_bytes

    grouped = log("A", "B")
    grouped = CaseLog(
        tuple(
            replace(trace, attributes=(CaseAttribute("group", "int", index),))
            for index, trace in enumerate(grouped.traces)
        )
    )
    results = (
        cluster_cases(log("A", "B")),
        cluster_case_attribute_groups(grouped, CaseAttributeClusteringSpec("group")),
        cluster_case_profiles(log("A", "B")),
        retrieve_similar_cases(log("A"), log("B")),
        compare_stochastic_languages(log("A"), log("B")),
        compare_stochastic_languages(
            log("A", "B"), log("A", "B"), LanguageDistanceSpec(max_augmentations=1)
        ),
        mine_decision_tree(
            log("A", "B"),
            (
                DecisionExample("c0", (2**53 + 1,), "L"),
                DecisionExample("c1", (2**53 + 2,), "R"),
            ),
            DecisionTreeSpec(("x",)),
        ),
        detect_bose_drift(log("AB", "BA"), BoseDriftSpec(sublog_size=1, window_size=1)),
        detect_bose_drift(log("A")),
        cluster_cases(CaseLog((CaseTrace("bad", (CaseEvent("e"),)),))),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result
