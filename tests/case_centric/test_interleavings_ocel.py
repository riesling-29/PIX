"""Interleaving-to-OCEL relation oracles and provenance counterexamples."""

import json
import math
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.interleavings import (
    CaseLink,
    InterleavingSpec,
    discover_interleavings,
)
from pix.case_centric.interleavings_ocel import (
    OPERATOR_ID,
    RESULT_SCHEMAS,
    InterleavingsOCELConversion,
    InterleavingsOCELReport,
    InterleavingsOCELSpec,
    from_interleavings,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseTrace,
    case_log_digest,
)
from pix.ocel import validate
from pix.ocel.canonical import canonical_digest
from pix.results import _decode, _encode, result_from_json, result_json_bytes

ORIGIN = datetime(2026, 9, 15, tzinfo=timezone.utc)


def event(identity, second, activity="a", extra=()):
    return CaseEvent(
        identity,
        (
            CaseAttribute("concept:name", "string", activity),
            CaseAttribute("time:timestamp", "date", ORIGIN + timedelta(seconds=second)),
            *extra,
        ),
    )


def sample(left_times=(0, 2), right_times=(1, 3)):
    left = CaseLog(
        (CaseTrace("same", tuple(event(str(i), t) for i, t in enumerate(left_times))),)
    )
    right = CaseLog(
        (CaseTrace("same", tuple(event(str(i), t) for i, t in enumerate(right_times))),)
    )
    spec = InterleavingSpec((CaseLink("same", "same"),), include_boundaries=False)
    return left, right, discover_interleavings(left, right, spec)


def entity_map(identities):
    return {(item.side, item.source_id): item.ocel_id for item in identities}


@pytest.mark.parametrize(
    "left_times,right_times,source_side,source_event,target_side",
    [((0, 2), (1, 3), "left", "0", "right"), ((1, 3), (0, 2), "right", "1", "left")],
)
def test_direction_adds_source_event_to_target_case(
    left_times, right_times, source_side, source_event, target_side
):
    left, right, parent = sample(left_times, right_times)
    projection = from_interleavings(left, right, parent)
    report = projection.evidence.value
    ocel = projection.require_ocel()
    assert projection.complete
    assert validate(ocel).valid
    assert len(ocel.events) == 4
    assert len(ocel.objects) == 2
    assert len(ocel.e2o) == 5
    assert report.witness_count == 1
    ids = entity_map(report.event_identities)
    cases = entity_map(report.object_identities)
    cross = report.cross_associations[0]
    assert cross.event_id == ids[source_side, source_event]
    assert cross.object_id == cases[target_side, "same"]
    assert cross.witness_indices == (0,)
    assert cross.qualifier == "interleaving_candidate"
    own = {(r.event, r.object) for r in ocel.e2o if r.qualifier == "case"}
    assert own == {(ocel_id, cases[side, "same"]) for (side, _), ocel_id in ids.items()}
    assert projection.left_log is left and projection.right_log is right
    assert report.ocel_digest == canonical_digest(ocel).identifier
    assert projection.evidence.parent_computation_ids == (parent.computation_id,)


def test_equal_native_event_and_case_ids_never_merge_sides_or_entity_kinds():
    source = CaseLog((CaseTrace('same:"left"', (event('same:"left"', 0),)),))
    parent = discover_interleavings(source, source)
    result = from_interleavings(source, source, parent)
    evidence = result.evidence.value
    ids = [v.ocel_id for v in (*evidence.event_identities, *evidence.object_identities)]
    assert len(set(ids)) == 4
    assert len(result.require_ocel().events) == 2
    assert len(result.require_ocel().objects) == 2
    assert evidence.cross_associations == ()


def test_all_events_and_empty_unlinked_cases_are_preserved():
    left, right, parent = sample()
    left = replace(
        left,
        traces=(
            *left.traces,
            CaseTrace("empty"),
            CaseTrace("unlinked", (event("u", 9),)),
        ),
    )
    right = replace(right, traces=(*right.traces, CaseTrace("empty")))
    parent = discover_interleavings(left, right, parent.spec)
    result = from_interleavings(left, right, parent)
    assert len(result.ocel.events) == 5
    assert len(result.ocel.objects) == 5
    assert result.evidence.value.own_case_relation_count == 5
    assert len(result.ocel.e2o) == 6


def test_boundary_endpoints_are_omitted_with_count_and_no_fabricated_events():
    left, right, parent = sample((0,), (1,))
    parent = discover_interleavings(
        left, right, replace(parent.spec, include_boundaries=True)
    )
    assert len(parent.value.witnesses) == 1
    result = from_interleavings(left, right, parent)
    assert result.evidence.status is ComputeStatus.PARTIAL
    assert not result.complete
    assert result.evidence.value.skipped_boundary_witness_indices == (0,)
    assert result.evidence.value.cross_associations == ()
    assert len(result.ocel.events) == len(result.ocel.e2o) == 2
    assert "boundary_associations_omitted" in {i.code for i in result.evidence.issues}


def test_every_witness_has_explicit_disposition_with_multiple_crossings():
    left, right, parent = sample((0, 2, 4), (1, 3, 5))
    result = from_interleavings(left, right, parent)
    report = result.evidence.value
    assert report.witness_count == 3
    assert sorted(i for a in report.cross_associations for i in a.witness_indices) == [
        0,
        1,
        2,
    ]
    assert len(result.ocel.e2o) == 9
    with pytest.raises(ValueError, match="exactly one disposition"):
        replace(report, witness_count=4)


def test_swapped_or_changed_source_rejects_stale_evidence():
    left, right, parent = sample()
    for changed_left, changed_right in (
        (right, left),
        (replace(left, metadata=(("changed", "true"),)), right),
        (left, replace(right, traces=(*right.traces, CaseTrace("new")))),
    ):
        result = from_interleavings(changed_left, changed_right, parent)
        assert result.evidence.status is ComputeStatus.INVALID_INPUT
        assert result.candidate is None
        assert result.evidence.issues[0].code == "interleaving_evidence_mismatch"


def test_supplied_digest_does_not_authorize_forged_witness_payload():
    left, right, parent = sample()
    forged = replace(parent, value=replace(parent.value, witnesses=()))
    assert forged.computation_id == parent.computation_id
    result = from_interleavings(left, right, forged)
    assert result.evidence.status is ComputeStatus.INVALID_INPUT
    assert result.candidate is None


@pytest.mark.parametrize(
    "field,new_value",
    [("operator_id", "forged"), ("computation_id", "forged"), ("issues", ())],
)
def test_parent_envelope_is_validated_not_only_its_source_digest(field, new_value):
    left, right, parent = sample()
    if field == "issues":
        from pix.contracts.result import ComputeIssue

        new_value = (ComputeIssue("forged", "fabricated issue"),)
    forged = replace(parent, **{field: new_value})
    assert (
        from_interleavings(left, right, forged).evidence.status
        is ComputeStatus.INVALID_INPUT
    )


def test_unavailable_parent_does_not_publish_an_empty_complete_ocel():
    left, right, parent = sample()
    parent = discover_interleavings(left, right, replace(parent.spec, max_events=1))
    result = from_interleavings(left, right, parent)
    assert result.evidence.status is ComputeStatus.UNAVAILABLE
    assert result.candidate is None
    with pytest.raises(ValueError):
        result.require_ocel()


@pytest.mark.parametrize(
    "attribute",
    [
        CaseAttribute("nested", "list", values=(CaseAttribute("v", "int", 1),)),
        CaseAttribute(
            "nested", "string", "v", children=(CaseAttribute("m", "int", 1),)
        ),
        CaseAttribute("x", "float", float("nan")),
        CaseAttribute("x", "float", float("inf")),
        CaseAttribute("x", "null"),
    ],
)
def test_unrepresentable_event_attributes_fail_without_altering_raw_sources(attribute):
    left, right, parent = sample()
    source_event = replace(
        left.traces[0].events[0],
        attributes=(*left.traces[0].events[0].attributes, attribute),
    )
    left = replace(
        left,
        traces=(
            replace(left.traces[0], events=(source_event, *left.traces[0].events[1:])),
        ),
    )
    digest = case_log_digest(left)
    parent = discover_interleavings(left, right, parent.spec)
    result = from_interleavings(left, right, parent)
    assert result.evidence.status is ComputeStatus.UNAVAILABLE
    assert result.candidate is None
    assert result.left_log is left
    assert case_log_digest(left) == digest
    assert result.evidence.issues[0].at[0] == "left"
    if attribute.type == "float" and math.isnan(attribute.value):
        assert math.isnan(result.left_log.traces[0].events[0].attributes[-1].value)


def test_unrepresentable_trace_attributes_are_reported():
    left, right, parent = sample()
    nested = CaseAttribute(
        "nested", "container", children=(CaseAttribute("a", "string", "b"),)
    )
    left = replace(left, traces=(replace(left.traces[0], attributes=(nested,)),))
    parent = discover_interleavings(left, right, parent.spec)
    result = from_interleavings(left, right, parent)
    assert result.candidate is None
    assert result.evidence.issues[0].at == ("left", "trace", "same")
    assert result.left_log.traces[0].attributes == (nested,)


def test_log_metadata_and_nested_log_attributes_remain_in_native_sidecars():
    left, right, parent = sample()
    nested = CaseAttribute(
        "metadata", "list", values=(CaseAttribute("n", "float", float("nan")),)
    )
    left = replace(
        left,
        attributes=(nested,),
        classifiers=(CaseClassifier("activity", ("concept:name",)),),
        metadata=(("xes.version", "1.0"),),
    )
    parent = discover_interleavings(left, right, parent.spec)
    result = from_interleavings(left, right, parent)
    assert result.complete
    assert result.left_log is left
    assert result.left_log.attributes[0] is nested
    assert result.evidence.value.transformations[0].startswith("native_sidecars:")


def test_missing_unlinked_event_timestamp_blocks_ocel_without_fabrication():
    left, right, parent = sample()
    missing = CaseEvent("missing", (CaseAttribute("concept:name", "string", "m"),))
    left = replace(left, traces=(*left.traces, CaseTrace("unlinked", (missing,))))
    parent = discover_interleavings(left, right, parent.spec)
    assert parent.status is ComputeStatus.COMPUTED
    result = from_interleavings(left, right, parent)
    assert result.candidate is None
    assert result.evidence.issues[0].code == "case_to_ocel_unrepresentable"
    assert "timestamp" in result.evidence.issues[0].message


def test_shared_event_types_merge_compatible_schema_declarations():
    left = CaseLog(
        (CaseTrace("c", (event("e", 0, extra=(CaseAttribute("l", "int", 1),)),)),)
    )
    right = CaseLog(
        (
            CaseTrace(
                "c", (event("e", 1, extra=(CaseAttribute("r", "boolean", True),)),)
            ),
        )
    )
    parent = discover_interleavings(left, right)
    result = from_interleavings(left, right, parent)
    assert result.complete
    assert len(result.ocel.event_types) == 1
    assert {a.name for a in result.ocel.event_types[0].attributes} == {
        "concept:name",
        "time:timestamp",
        "l",
        "r",
    }


def test_conflicting_cross_log_schema_requires_explicit_side_scope():
    left = CaseLog(
        (CaseTrace("c", (event("e", 0, extra=(CaseAttribute("x", "int", 1),)),)),)
    )
    right = CaseLog(
        (CaseTrace("c", (event("e", 1, extra=(CaseAttribute("x", "string", "1"),)),)),)
    )
    parent = discover_interleavings(left, right)
    shared = from_interleavings(left, right, parent)
    assert shared.candidate is None
    assert shared.evidence.issues[0].code == "cross_log_event_schema_conflict"
    separate = from_interleavings(
        left, right, parent, InterleavingsOCELSpec(event_type_scope="side")
    )
    assert separate.complete
    assert len(separate.ocel.event_types) == 2
    assert len({i.ocel_id for i in separate.evidence.value.event_type_identities}) == 2
    assert separate.evidence.computation_id != shared.evidence.computation_id


def test_custom_keys_global_defaults_and_custom_qualifiers_are_projected():
    def custom(second):
        return CaseLog(
            (
                CaseTrace(
                    "c",
                    (
                        CaseEvent(
                            "e",
                            (
                                CaseAttribute(
                                    "when", "date", ORIGIN + timedelta(seconds=second)
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            globals=(
                CaseGlobal("event", (CaseAttribute("act", "string", "common"),)),
                CaseGlobal(
                    "trace", (CaseAttribute("customer", "id", "C", lexical="C"),)
                ),
            ),
        )

    left, right = custom(0), custom(1)
    parent = discover_interleavings(
        left,
        right,
        InterleavingSpec(
            left_timestamp_key="when",
            right_timestamp_key="when",
            left_activity_key="act",
            right_activity_key="act",
        ),
    )
    spec = InterleavingsOCELSpec("orders", "deliveries", "belongs_to", "candidate")
    result = from_interleavings(left, right, parent, spec)
    assert result.complete
    assert {o.type for o in result.ocel.objects} == {"orders", "deliveries"}
    assert {e.type for e in result.ocel.events} == {"common"}
    assert {r.qualifier for r in result.ocel.e2o} == {"belongs_to"}
    assert all(o.attributes[0].value == "C" for o in result.ocel.objects)
    assert all(not trace.attributes for log in (left, right) for trace in log.traces)
    assert all(
        len(e.attributes) == 1
        for log in (left, right)
        for t in log.traces
        for e in t.events
    )


def test_empty_sources_produce_valid_empty_ocel_without_synthetic_entities():
    left, right = CaseLog(), CaseLog()
    result = from_interleavings(left, right, discover_interleavings(left, right))
    assert result.complete
    assert result.ocel.events == result.ocel.objects == result.ocel.e2o == ()
    assert result.evidence.value.witness_count == 0


@pytest.mark.parametrize(
    "spec,code",
    [
        (InterleavingsOCELSpec(max_events=4), "interleavings_ocel_event_limit"),
        (InterleavingsOCELSpec(max_objects=2), "interleavings_ocel_object_limit"),
        (InterleavingsOCELSpec(max_relations=5), "interleavings_ocel_relation_limit"),
    ],
)
def test_whole_input_limits_include_unselected_population(spec, code):
    left, right, parent = sample()
    left = replace(
        left, traces=(*left.traces, CaseTrace("unlinked", (event("extra", 9),)))
    )
    parent = discover_interleavings(left, right, replace(parent.spec, max_events=4))
    assert parent.value.linked_event_count == 4
    result = from_interleavings(left, right, parent, spec)
    assert result.evidence.status is ComputeStatus.UNAVAILABLE
    assert result.candidate is None
    assert result.evidence.issues[0].code == code
    assert result.left_log is left


def test_exact_relation_limit_accepts_complete_population():
    left, right, parent = sample()
    result = from_interleavings(
        left, right, parent, InterleavingsOCELSpec(max_relations=5)
    )
    assert result.complete
    assert len(result.ocel.e2o) == 5


def test_public_result_persistence_roundtrips_all_terminal_statuses():
    left, right, parent = sample()
    computed = from_interleavings(left, right, parent).evidence
    unavailable = from_interleavings(
        left, right, parent, InterleavingsOCELSpec(max_events=1)
    ).evidence
    invalid = from_interleavings(
        left, right, replace(parent, value=replace(parent.value, witnesses=()))
    ).evidence
    single_left, single_right, single_parent = sample((0,), (1,))
    single_parent = discover_interleavings(
        single_left, single_right, replace(single_parent.spec, include_boundaries=True)
    )
    partial = from_interleavings(single_left, single_right, single_parent).evidence
    assert {r.status for r in (computed, partial, unavailable, invalid)} == set(
        ComputeStatus
    )
    for evidence in (computed, partial, unavailable, invalid):
        assert result_from_json(result_json_bytes(evidence)) == evidence


def test_report_and_spec_are_frozen_and_typed_json_roundtrip():
    left, right, parent = sample()
    conversion = from_interleavings(left, right, parent)
    report = conversion.evidence.value
    _, spec_type, report_type = RESULT_SCHEMAS[OPERATOR_ID]
    assert spec_type is InterleavingsOCELSpec
    assert report_type is InterleavingsOCELReport
    assert _decode(json.loads(json.dumps(_encode(report))), report_type) == report
    assert (
        _decode(json.loads(json.dumps(_encode(conversion.evidence.spec))), spec_type)
        == conversion.evidence.spec
    )
    with pytest.raises(FrozenInstanceError):
        report.witness_count = 99
    with pytest.raises(ValueError, match="digest"):
        replace(conversion, candidate=replace(conversion.candidate, e2o=()))
    with pytest.raises(ValueError, match="sidecars"):
        replace(conversion, left_log=CaseLog())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"left_object_type": "right_case"},
        {"event_type_scope": "automatic"},
        {"own_case_qualifier": "interleaving_candidate"},
        {"left_object_type": ""},
        {"max_events": 0},
        {"max_objects": False},
        {"max_relations": -1},
    ],
)
def test_invalid_specs_reject_ambiguous_mapping(kwargs):
    with pytest.raises(ValueError):
        InterleavingsOCELSpec(**kwargs)


def test_conversion_rejects_non_case_input_and_non_interleaving_parent():
    left, right, parent = sample()
    with pytest.raises(TypeError):
        from_interleavings([], right, parent)
    with pytest.raises(TypeError):
        from_interleavings(left, right, "parent")
    with pytest.raises(TypeError):
        from_interleavings(left, right, parent, "mapping")
    with pytest.raises(TypeError):
        InterleavingsOCELConversion(left, right, None, "evidence")
