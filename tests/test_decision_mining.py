"""Decision observations must be grounded in prior events and actual firings."""

from dataclasses import replace

import pytest

from pix.case_centric.advanced import GuardCondition
from pix.case_centric.decision_mining import (
    DataGuardClause,
    DataPetriNetMiningSpec,
    DecisionFeatureSpec,
    DecisionFeatureValue,
    DecisionTableSpec,
    TransitionDataGuard,
    data_petri_net_digest,
    discover_decision_points,
    evaluate_data_guards,
    extract_decision_table,
    fire_data_transition,
    mine_data_petri_net,
)
from pix.compute.conformance import align_traces
from pix.compute.replay import replay_traces
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def net(duplicate_label=False, loop=False):
    return PetriNet(
        tuple(Place(place) for place in ("start", "choice", "end")),
        (
            Transition("tA", "A"),
            Transition("tB", "B"),
            Transition("tC", "B" if duplicate_label else "C"),
        ),
        (
            Arc("start", "tA"),
            Arc("tA", "choice"),
            Arc("choice", "tB"),
            Arc("tB", "choice" if loop else "end"),
            Arc("choice", "tC"),
            Arc("tC", "end"),
        ),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )


def log(*cases):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"c{i}:e{j}",
                        (CaseAttribute("concept:name", "string", activity),)
                        + (
                            ()
                            if amount is None
                            else (CaseAttribute("amount", "int", amount),)
                        ),
                    )
                    for j, (activity, amount) in enumerate(case)
                ),
            )
            for i, case in enumerate(cases)
        )
    )


def spec(**kwargs):
    return DecisionTableSpec((DecisionFeatureSpec("amount", "amount"),), **kwargs)


def training_log():
    return log((("A", 10), ("B", 999)), (("A", 20), ("C", 999)))


def fitted_model(method="alignment"):
    table = extract_decision_table(training_log(), net(), spec(method=method))
    result = mine_data_petri_net(table, net())
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value.model


@pytest.mark.parametrize("method", ["alignment", "replay"])
def test_actual_firing_table_uses_predecision_attribute_not_selected_event(method):
    result = extract_decision_table(training_log(), net(), spec(method=method))
    assert result.status is ComputeStatus.COMPUTED, result.issues
    table = result.value
    assert table.eligible_row_count == 2
    assert tuple(row.transition_id for row in table.observations) == ("tB", "tC")
    assert tuple(row.features[0].value for row in table.observations) == (10, 20)
    assert tuple(row.features[0].source_event_id for row in table.observations) == (
        "c0:e0",
        "c1:e0",
    )
    assert all(
        row.prefix_event_count == 1 and row.marking_before == Marking((("choice", 1),))
        for row in table.observations
    )
    assert len(result.parent_computation_ids) == 2


@pytest.mark.parametrize("method", ["alignment", "replay"])
def test_public_existing_witness_is_verified_and_reusable(method):
    dataset, model = training_log(), net()
    traces = case_traces(dataset)
    witness = (
        align_traces(traces, model)
        if method == "alignment"
        else replay_traces(traces, model)
    )
    explicit = extract_decision_table(
        dataset, model, spec(method=method), witness=witness
    )
    implicit = extract_decision_table(dataset, model, spec(method=method))
    assert explicit == implicit
    with pytest.raises(ValueError, match="identity does not match"):
        extract_decision_table(
            log((("A", 55), ("B", 999))), model, spec(method=method), witness=witness
        )


def test_tampered_alignment_firing_is_rejected_without_trusting_envelope_only():
    dataset, model = training_log(), net()
    witness = align_traces(case_traces(dataset), model)
    case = witness.value.alignments[0]
    broken = replace(case.moves[-1], after_marking=(("choice", 1),))
    tampered_case = replace(case, moves=case.moves[:-1] + (broken,))
    tampered = replace(
        witness,
        value=replace(
            witness.value, alignments=(tampered_case,) + witness.value.alignments[1:]
        ),
    )
    with pytest.raises(ValueError, match="valid model firing"):
        extract_decision_table(dataset, model, spec(), witness=tampered)


def test_witness_parameters_must_match_the_declared_request():
    dataset, model = training_log(), net()
    different = AlignmentSpec(synchronous_move_cost=2)
    witness = align_traces(case_traces(dataset), model, different)
    with pytest.raises(ValueError, match="identity does not match"):
        extract_decision_table(dataset, model, spec(), witness=witness)
    accepted = extract_decision_table(
        dataset, model, spec(alignment_spec=different), witness=witness
    )
    assert accepted.status is ComputeStatus.COMPUTED


def test_row_limit_uses_source_case_order_even_for_reordered_witness_array():
    dataset, model = training_log(), net()
    witness = align_traces(case_traces(dataset), model)
    reordered = replace(
        witness,
        value=replace(
            witness.value, alignments=tuple(reversed(witness.value.alignments))
        ),
    )
    first = extract_decision_table(dataset, model, spec(max_rows=1), witness=witness)
    second = extract_decision_table(dataset, model, spec(max_rows=1), witness=reordered)
    assert first.value.observations == second.value.observations
    assert second.value.observations[0].case_id == "c0"
    assert first.spec.witness_payload_digest != second.spec.witness_payload_digest


def test_decision_row_rejects_future_or_inconsistent_feature_evidence():
    row = extract_decision_table(training_log(), net(), spec()).value.observations[0]
    feature = row.features[0]
    with pytest.raises(ValueError, match="precede"):
        replace(
            row, features=(replace(feature, source_event_index=row.prefix_event_count),)
        )
    with pytest.raises(ValueError, match="unobserved"):
        replace(
            feature,
            status="missing",
            value=999,
            source_event_id=None,
            source_event_index=None,
        )
    with pytest.raises(ValueError, match="eligibility"):
        replace(row, eligible=True, reasons=("feature_missing:amount",))


def test_decision_table_rejects_false_coverage_and_foreign_labels():
    table = extract_decision_table(training_log(), net(), spec()).value
    with pytest.raises(ValueError, match="coverage"):
        replace(table, eligible_row_count=999)
    row = table.observations[0]
    with pytest.raises(ValueError, match="population"):
        replace(
            table,
            observations=(replace(row, case_id="foreign"),) + table.observations[1:],
        )


@pytest.mark.parametrize("method", ["alignment", "replay"])
def test_duplicate_transition_labels_keep_ids_and_default_ambiguity_exclusion(method):
    dataset, model = log((("A", 10), ("B", 999))), net(duplicate_label=True)
    excluded = extract_decision_table(dataset, model, spec(method=method))
    assert excluded.status is ComputeStatus.PARTIAL
    row = excluded.value.observations[0]
    assert row.same_label_enabled_branch_ids == ("tB", "tC")
    assert row.transition_id in ("tB", "tC")
    assert not row.eligible
    assert row.reasons == ("ambiguous_transition_label",)
    selected = extract_decision_table(
        dataset, model, spec(method=method, ambiguous_label_policy="selected_witness")
    )
    assert selected.status is ComputeStatus.COMPUTED
    assert selected.value.observations[0].transition_id == row.transition_id


def test_loop_has_separate_decision_occurrences_with_strict_prefixes():
    dataset = log((("A", 1), ("B", 2), ("B", 3), ("C", 4)))
    result = extract_decision_table(dataset, net(loop=True), spec())
    assert result.status is ComputeStatus.COMPUTED
    rows = result.value.observations
    assert len({row.row_id for row in rows}) == 3
    assert tuple(row.case_id for row in rows) == ("c0",) * 3
    assert tuple(row.features[0].value for row in rows) == (1, 2, 3)
    fitted = mine_data_petri_net(result, net(loop=True))
    assert fitted.value.training_observation_count == 3
    assert fitted.value.model.decisions[0].training_case_ids == ("c0",)


def test_silent_branch_observes_only_events_before_silent_firing():
    model = PetriNet(
        tuple(Place(place) for place in ("s", "p", "left", "right", "f")),
        (
            Transition("a", "A"),
            Transition("tauL"),
            Transition("tauR"),
            Transition("b", "B"),
            Transition("c", "C"),
        ),
        tuple(
            Arc(a, b)
            for a, b in (
                ("s", "a"),
                ("a", "p"),
                ("p", "tauL"),
                ("tauL", "left"),
                ("p", "tauR"),
                ("tauR", "right"),
                ("left", "b"),
                ("b", "f"),
                ("right", "c"),
                ("c", "f"),
            )
        ),
        Marking((("s", 1),)),
        Marking((("f", 1),)),
    )
    result = extract_decision_table(training_log(), model, spec())
    assert result.status is ComputeStatus.COMPUTED
    assert tuple(row.transition_id for row in result.value.observations) == (
        "tauL",
        "tauR",
    )
    assert tuple(row.features[0].value for row in result.value.observations) == (10, 20)
    assert all(
        row.event_id is None and row.prefix_event_count == 1
        for row in result.value.observations
    )


def test_missing_feature_is_retained_and_case_initial_scope_requires_explicit_request():
    dataset = log((("A", None), ("B", 999)))
    dataset = CaseLog(
        (replace(dataset.traces[0], attributes=(CaseAttribute("amount", "int", 17),)),)
    )
    ordinary = extract_decision_table(dataset, net(), spec())
    assert ordinary.status is ComputeStatus.PARTIAL
    assert ordinary.value.observations[0].features[0].status == "missing"
    declared = extract_decision_table(
        dataset,
        net(),
        DecisionTableSpec(
            (DecisionFeatureSpec("initial", "amount", "case_declared_initial"),)
        ),
    )
    assert declared.value.observations[0].features[0].value == 17
    assert declared.value.observations[0].features[0].source_event_id is None


@pytest.mark.parametrize("method", ["alignment", "replay"])
def test_nonfitting_cases_are_not_treated_as_branch_training_evidence(method):
    dataset = log((("X", 12), ("B", 999)))
    result = extract_decision_table(dataset, net(), spec(method=method))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.observations == ()
    assert result.value.excluded_cases[0].reason == "nonfitting_witness"


def test_alignment_limit_and_row_limit_remain_explicit():
    limited = extract_decision_table(
        training_log(), net(), spec(alignment_spec=AlignmentSpec(max_states=1))
    )
    assert limited.status is ComputeStatus.PARTIAL
    assert limited.value.eligible_row_count == 0
    assert all(item.reason == "search_limit" for item in limited.value.excluded_cases)
    capped = extract_decision_table(training_log(), net(), spec(max_rows=1))
    assert capped.status is ComputeStatus.PARTIAL
    assert capped.value.decision_occurrence_count == 2
    assert capped.value.omitted_row_count == 1


@pytest.mark.parametrize("method", ["alignment", "replay"])
def test_fitted_data_petri_net_guards_evaluate_and_fire_with_token_semantics(method):
    model = fitted_model(method)
    marking = Marking((("choice", 1),))
    values = (DecisionFeatureValue("amount", 15),)
    left = evaluate_data_guards(model, marking, "tB", values).value
    right = evaluate_data_guards(model, marking, "tC", values).value
    assert (
        left.structurally_enabled
        and left.guard_state == "false"
        and left.enabled is False
    )
    assert (
        right.structurally_enabled
        and right.guard_state == "true"
        and right.enabled is True
    )
    assert (
        fire_data_transition(model, marking, "tC", values) == model.base.final_marking
    )
    with pytest.raises(ValueError, match="not enabled"):
        fire_data_transition(model, marking, "tB", values)
    assert marking == Marking((("choice", 1),))


def test_missing_guard_value_is_unknown_and_cannot_fire():
    model = fitted_model()
    marking = Marking((("choice", 1),))
    result = evaluate_data_guards(model, marking, "tB").value
    assert result.guard_state == "unknown" and result.enabled is None
    assert result.decisions[0].missing_features == ("amount",)
    with pytest.raises(ValueError, match="unknown"):
        fire_data_transition(model, marking, "tB")
    disabled = evaluate_data_guards(model, model.base.initial_marking, "tB").value
    assert disabled.enabled is False and disabled.guard_state == "unknown"
    unchanged = evaluate_data_guards(model, model.base.initial_marking, "tA").value
    assert unchanged.enabled is True and unchanged.guard_state == "true"


def test_training_case_split_keeps_all_occurrences_together_and_freezes_guards():
    table = extract_decision_table(training_log(), net(), spec())
    result = mine_data_petri_net(
        table, net(), DataPetriNetMiningSpec(training_case_ids=("c0",))
    )
    assert result.status is ComputeStatus.COMPUTED
    point = result.value.model.decisions[0]
    assert point.training_case_ids == ("c0",)
    assert all('"c0"' in row_id for row_id in point.training_row_ids)
    digest = data_petri_net_digest(result.value.model)
    evaluate_data_guards(
        result.value.model,
        Marking((("choice", 1),)),
        "tB",
        (DecisionFeatureValue("amount", 12345),),
    )
    assert data_petri_net_digest(result.value.model) == digest
    unobserved_branch = next(
        guard for guard in point.guards if guard.transition_id == "tC"
    )
    assert unobserved_branch.clauses == ()


def test_untrained_decision_is_unknown_not_unconditionally_allowed():
    table = extract_decision_table(log((("A", None), ("B", 999))), net(), spec())
    fitted = mine_data_petri_net(table, net())
    assert fitted.status is ComputeStatus.PARTIAL
    model = fitted.value.model
    assert model.decisions[0].status == "untrained"
    assert (
        evaluate_data_guards(model, Marking((("choice", 1),)), "tB").value.enabled
        is None
    )


def test_guard_boolean_logic_is_three_valued_without_eval():
    model = fitted_model()
    false_and_unknown = DataGuardClause(
        (GuardCondition(0, "amount", "<=", 10), GuardCondition(0, "amount", ">", 10))
    )
    always_true = DataGuardClause(())
    point = model.decisions[0]
    guards = (
        TransitionDataGuard("tB", (false_and_unknown, always_true), 1),
        TransitionDataGuard("tC", (), 1),
    )
    altered = replace(model, decisions=(replace(point, guards=guards),))
    result = evaluate_data_guards(altered, Marking((("choice", 1),)), "tB").value
    assert result.guard_state == "true" and result.enabled is True
    assert result.decisions[0].clause_states == ("unknown", "true")


def test_data_petri_net_rejects_bad_guard_schema_and_foreign_place():
    model = fitted_model()
    point = model.decisions[0]
    with pytest.raises(ValueError, match="invalid typed numeric condition"):
        replace(
            model,
            decisions=(
                replace(
                    point,
                    guards=(
                        TransitionDataGuard(
                            "tB",
                            (DataGuardClause((GuardCondition(0, "WRONG", "<=", 0),)),),
                            1,
                        ),
                        point.guards[1],
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="base net"):
        replace(model, decisions=(replace(point, place_id="foreign"),))
    with pytest.raises(ValueError, match="finite"):
        DecisionFeatureValue("amount", float("nan"))


def test_public_persistence_roundtrip_table_data_model_result_and_guard_evaluation():
    from pix.results import result_from_json, result_json_bytes

    table = extract_decision_table(training_log(), net(), spec())
    fitted = mine_data_petri_net(table, net())
    evaluation = evaluate_data_guards(
        fitted.value.model, Marking((("choice", 1),)), "tB"
    )
    for result in (
        table,
        fitted,
        evaluation,
        extract_decision_table(log((("A", None), ("B", 3))), net(), spec()),
    ):
        assert result_from_json(result_json_bytes(result)) == result


def test_nonchoice_selection_and_model_mismatch_are_rejected():
    assert discover_decision_points(net())[0].transition_ids == ("tB", "tC")
    with pytest.raises(ValueError, match="structural choice"):
        extract_decision_table(training_log(), net(), spec(places=("start",)))
    table = extract_decision_table(training_log(), net(), spec())
    with pytest.raises(ValueError, match="differs"):
        mine_data_petri_net(table, net(loop=True))
