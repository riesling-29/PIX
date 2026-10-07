"""Executable MODEL/W4 review with independent small domain expectations.

The example owns its input fixtures; this test owns the expected answers.
Passing these cases is evidence for the named profiles, not upstream parity.
"""

from collections import Counter, deque
from importlib import import_module
from itertools import product
from pathlib import Path
from runpy import run_path

import pytest

from pix._mining_registry import mining_schemas
from pix.contracts.result import ComputeStatus
from pix.results import (
    read_result,
    result_from_json,
    result_json_bytes,
    write_result,
)

EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "examples/models_w4_review.py"
EXAMPLE = run_path(str(EXAMPLE_PATH))
CASE_NAMES = tuple(EXAMPLE["review_notes"]())


@pytest.fixture(scope="module")
def cases():
    return EXAMPLE["build_review_cases"]()


def _finite_words(tree):
    """Interpret finite sequence/XOR trees without calling PIX algorithms."""
    if tree.operator == "tau":
        return {""}
    if tree.operator == "activity":
        return {tree.activity}
    parts = [_finite_words(child) for child in tree.children]
    if tree.operator == "xor":
        return set().union(*parts)
    assert tree.operator == "sequence", tree.operator
    return {"".join(word) for word in product(*parts)}


def _net_words(net):
    """Independent incidence arithmetic for the finite conversion fixtures."""
    initial = (net.initial_marking.tokens, ())
    queue, seen, accepted = deque([initial]), {initial}, set()
    while queue:
        marking, word = queue.popleft()
        if marking == net.final_marking.tokens:
            accepted.add("".join(word))
        for transition in net.transitions:
            consume = Counter(
                {a.source: a.weight for a in net.arcs if a.target == transition.id}
            )
            produce = Counter(
                {a.target: a.weight for a in net.arcs if a.source == transition.id}
            )
            tokens = Counter(dict(marking))
            if any(tokens[p] < count for p, count in consume.items()):
                continue
            tokens.subtract(consume)
            tokens.update(produce)
            next_word = (
                word if transition.activity is None else (*word, transition.activity)
            )
            following = (
                tuple(sorted((p, count) for p, count in tokens.items() if count)),
                next_word,
            )
            if following not in seen:
                seen.add(following)
                queue.append(following)
        assert len(seen) < 1000, "Finite review fixture unexpectedly expands"
    return accepted


def test_review_notes_and_observations_cover_exact_actual_cases(cases):
    assert cases.keys() == EXAMPLE["review_notes"]().keys()
    assert cases.keys() == EXAMPLE["review_observations"](cases).keys()
    assert len(cases) == 32
    assert len({result.operator_id for result in cases.values()}) == len(cases)
    for name, result in cases.items():
        expected = (
            ComputeStatus.PARTIAL
            if name == "case_stream_revision"
            else ComputeStatus.COMPUTED
        )
        assert result.status is expected, (name, result.issues)
        assert result.value is not None


def test_every_new_result_operator_has_a_live_review_case(cases):
    module_names = (
        "case_centric.coverability",
        "case_centric.decision_evaluation",
        "case_centric.drift_evaluation",
        "case_centric.feature_dataset",
        "case_centric.maximal_decomposition",
        "case_centric.model_labels",
        "case_centric.powl_conversion",
        "case_centric.resource_simulation",
        "case_centric.revisable_stream",
        "case_centric.timed_playout",
        "case_centric.tree_bordered",
        "case_centric.trie_conversion",
        "object_centric.action_planning",
        "object_centric.learning",
        "object_centric.operational_impact",
        "object_centric.revisable_stream",
        "object_centric.subprocess",
    )
    expected = {"pix.case_centric.discover_inductive_strict"}
    for name in module_names:
        expected.update(import_module(f"pix.{name}").RESULT_SCHEMAS)
    assert expected == {result.operator_id for result in cases.values()}
    registered = mining_schemas()
    assert expected <= registered.keys()


@pytest.mark.parametrize("name", CASE_NAMES)
def test_review_result_public_json_and_atomic_file_roundtrip(cases, name, tmp_path):
    result = cases[name]
    payload = result_json_bytes(result)
    restored = result_from_json(payload)
    assert restored == result
    assert restored.computation_id == result.computation_id
    assert result_json_bytes(restored) == payload
    destination = tmp_path / f"{name}.json"
    write_result(result, destination)
    assert read_result(destination) == result
    assert destination.read_bytes() == payload


def test_review_computations_are_repeatable(cases):
    repeated = EXAMPLE["build_review_cases"]()
    assert repeated == cases
    assert {name: result_json_bytes(r) for name, r in repeated.items()} == {
        name: result_json_bytes(r) for name, r in cases.items()
    }


def test_conversion_languages_and_occurrences(cases):
    parallel = cases["powl_to_tree"].value.model
    assert parallel.operator == "parallel"
    assert sorted(child.activity for child in parallel.children) == ["A", "B"]
    assert _net_words(cases["transition_bordered"].value.model) == {"AB"}
    assert _net_words(cases["trie_to_net"].value.model) == {"A", "AB"}
    assert _finite_words(cases["strict_inductive"].value) == {"A", "ABC"}
    before = cases["activity_labels"].value.occurrences
    after = cases["rename_labels"].value.occurrences
    assert [(o.node_id, o.activity) for o in before] == [("a", "A"), ("b", "B")]
    assert [(o.node_id, o.activity) for o in after] == [("a", "Approve"), ("b", "B")]
    assert [o.occurrence_id for o in before] == [o.occurrence_id for o in after]


def test_ordinary_net_coverability_and_exact_recomposition(cases):
    reachable = cases["coverability"].value
    assert reachable.bounded is True
    assert reachable.target_coverable is True
    decomposition = cases["maximal_decomposition"].value
    assert len(decomposition.components) == 3
    assert decomposition.certificate.identical_structure is True
    assert decomposition.certificate.identical_markings is True
    assert cases["maximal_recomposition"].value == EXAMPLE["_sequence_net"]()


def test_observation_cutoff_censoring_and_train_only_vocabulary(cases):
    dataset = cases["observation_dataset"].value
    assert [sample.prefix.length for sample in dataset.samples] == [2, 2]
    completed, censored = dataset.targets
    assert completed.next_activity == "C"
    assert completed.next_time_seconds == 5.0
    assert completed.remaining_time_seconds == 7.0
    assert completed.completion_status == "completed"
    assert censored.completion_status == "censored"
    assert censored.remaining_time_seconds is None
    encoder = cases["observation_encoder"].value.fitted_model
    assert encoder.training_case_ids == ("case-0",)
    assert [column.terms for column in encoder.columns] == [("A",), ("B",)]
    matrix = cases["observation_matrix"].value
    assert [row.values for row in matrix.matrix.rows] == [(1.0, 0.0), (0.0, 1.0)] * 2
    for row in cases["case_sequence_tensor"].value.rows:
        assert row.event_mask == (True, True, False)
        assert row.event_ids[-1] is None
        assert row.values[-1] == (None, None)
        assert row.known_masks[-1] == (False, False)


def test_connected_shared_groups_remain_atomic(cases):
    split = cases["leakage_split"].value
    assert {frozenset(group) for group in split.atomic_case_groups} == {
        frozenset(("case-0", "case-1", "case-2")),
        frozenset(("case-3",)),
    }
    partitions = split.partitions
    for ids in (
        partitions.train_case_ids,
        partitions.validation_case_ids,
        partitions.test_case_ids,
    ):
        intersection = set(ids) & {"case-0", "case-1", "case-2"}
        assert intersection in (set(), {"case-0", "case-1", "case-2"})


def test_held_out_decisions_and_no_spurious_drift(cases):
    assert cases["decision_evaluation"].value.occurrence_accuracy.as_fraction() == 1
    drift = cases["drift_adjustment"].value
    assert drift.windows
    assert all(row.adjusted_p_value.as_fraction() == 1 for row in drift.windows)
    assert drift.rejected_boundaries == ()


def test_queue_arithmetic_and_timed_token_reservation(cases):
    events = cases["resource_simulation"].value.repetitions[0].events
    assert [event.completion_seconds for event in events] == [2.0, 4.0]
    assert [event.waiting_seconds for event in events] == [0.0, 2.0]
    difference = cases["resource_comparison"].value.differences[0]
    assert difference.paired_completed_case_ids == ("job-1", "job-2")
    assert difference.mean_paired_flow_difference_seconds == -1.0
    fitted = cases["resource_duration_fit"].value.activities[0]
    assert fitted.observed_count == 2
    assert fitted.observed_mean_seconds == 3.0
    timed = cases["timed_playout"].value.runs[0]
    assert timed.completion_seconds == 5.0
    assert [(e.start_seconds, e.completion_seconds) for e in timed.events] == [
        (0.0, 2.0),
        (2.0, 5.0),
    ]


def test_late_case_event_retracts_edge_and_shared_event_merges_executions(cases):
    snapshot = cases["case_stream_revision"].value
    assert {(e.source, e.target): e.count for e in snapshot.dfg.edges} == {
        ("A", "B"): 1,
        ("B", "C"): 1,
    }
    edge_delta = {
        change.key: change.delta
        for change in snapshot.changes
        if change.metric == "edge"
    }
    assert edge_delta == {("A", "B"): 1, ("A", "C"): -1, ("B", "C"): 1}
    assert len(cases["object_stream_revision"].value.executions.executions) == 1


def test_required_action_precedence_and_matching_witness(cases):
    plan = cases["action_plan"].value
    assert plan.outcome == "optimal"
    assert plan.objective_value == 3
    assert plan.witness.makespan_us == 3
    assert plan.no_action_feasible is False
    first, second = plan.witness.actions
    assert second.start == first.end
    assert (second.end - first.start).total_seconds() == 0.000003
    matches = cases["action_matches"].value
    assert matches.matching_complete is True
    assert len(matches.alternatives) == 1


def test_operational_snapshot_counts_one_shared_event_and_two_objects(cases):
    impact = cases["operational_impact"].value
    assert impact.baseline.processed_event_ids == ()
    assert impact.scenario.processed_event_ids == ("e0",)
    delta = impact.typed_deltas[0]
    assert (delta.prior.total_count, delta.posterior.total_count) == (-2, 2)
    assert delta.prior.lost_object_ids == ("i1", "i2")
    assert delta.posterior.gained_object_ids == ("i1", "i2")
    assert (
        impact.interpretation
        == "model_inferred_population_difference_not_causal_effect"
    )


def test_object_subprocess_preserves_inside_and_accounts_for_outside(cases):
    subprocess = cases["object_subprocess"].value
    assert {p.id for p in subprocess.model.places} == {"p", "q"}
    assert {t.id for t in subprocess.model.transitions} == {"a"}
    assert {
        (t.place_id, t.object_id) for t in subprocess.omitted_final_marking.tokens
    } == {("r", "i1"), ("r", "i2")}
    pipeline = cases["object_subprocess_pipeline"].value
    assert {p.id for p in pipeline.profile.model.places} == {"p", "q"}
    assert pipeline.boundary_removed_place_ids == ("r",)


def test_known_linear_relation_is_fit_and_evaluated_on_unseen_object(cases):
    dataset = cases["object_k_step"].value
    assert (len(dataset.samples), dataset.k, dataset.horizon) == (5, 1, 1)
    fitted = cases["object_regression_fit"].value
    assert fitted.coefficients[0] == pytest.approx((2.0,))
    assert fitted.intercepts == pytest.approx((1.0,))
    predictions = cases["object_regression_predict"].value
    assert len(predictions.rows) == 1
    assert predictions.rows[0].values == pytest.approx((9.0,))
    errors = cases["object_regression_evaluation"].value.targets
    assert errors[0].evaluated_count == 1
    assert errors[0].mean_absolute_error == pytest.approx(0.0, abs=1e-12)
    inverse = cases["object_feature_inverse"].value
    assert sorted(row.cells[0].real for row in inverse.rows) == pytest.approx(
        [0, 1, 1, 2, 3, 3, 4, 5, 7, 9]
    )


def test_xml_exchange_semantics_and_extended_firing_arithmetic():
    exchanges = EXAMPLE["build_exchange_examples"]()
    assert set(exchanges) == {"pnml", "ptml", "bpmn"}
    for exchange in exchanges.values():
        assert exchange["semantic_roundtrip_equal"] is True
        assert exchange["second_roundtrip_equal"] is True
    extended = EXAMPLE["build_extended_net_examples"]()
    reset = extended["reset_inhibitor"]
    assert reset["enabled"] is True
    assert reset["after"] == (("p", 3), ("q", 4), ("r", 1))
    assert reset["inhibitor_at_threshold_enabled"] is False
    choice = extended["stochastic_choice"]
    assert choice["probabilities"] == (("a", 0.25), ("b", 0.75))


def test_generated_report_is_portable_and_contains_every_actual_result(cases, tmp_path):
    generated = EXAMPLE["write_review"](tmp_path)
    assert generated == cases
    text = (tmp_path / "REVIEW.md").read_text(encoding="utf-8")
    assert "PIX 모델" in text
    assert "알 수 없" in text
    for name, result in cases.items():
        assert f"## {name}" in text
        assert read_result(tmp_path / f"{name}.json") == result
    for suffix in ("pnml", "ptml", "bpmn"):
        assert (tmp_path / f"model.{suffix}").is_file()
