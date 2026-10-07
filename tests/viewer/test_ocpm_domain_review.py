"""Hand-counted OC review cases through existing result/view contracts."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix import case_centric as cc
from pix.compute.ocdfg import discover_ocdfg
from pix.contracts.analysis import OCDFGSpec
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    project_object_cases,
)
from pix.object_centric.conformance import (
    ObjectReplaySpec,
    replay_flattened_object_log,
    replay_object_log,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization
from pix.viewer.visualization import build_visualization


def log(rows):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(EventType(a) for a in sorted({row[1] for row in rows})),
        object_types=(ObjectType("T"),),
        objects=(Object("x", "T"), Object("y", "T")),
        events=tuple(
            Event(eid, activity, origin + timedelta(seconds=i))
            for i, (eid, activity, _) in enumerate(rows)
        ),
        e2o=tuple(
            E2O(eid, oid, role) for eid, _, relations in rows for oid, role in relations
        ),
    )


def test_hand_count_survives_visual_serialization_with_multiple_qualifiers():
    source = log(
        (
            ("e1", "A", (("x", "flow"), ("x", "audit"), ("y", "flow"))),
            ("e2", "B", (("x", "flow"), ("y", "flow"))),
            ("e3", "A", (("x", "flow"),)),
            ("e4", "B", (("x", "flow"),)),
        )
    )
    result = discover_ocdfg(source, OCDFGSpec(("T",)))
    document = loads_visualization(dumps_visualization(build_visualization(result)))
    graph = next(panel for panel in document.panels if panel.id == "oc-dfg")
    labels = {node.id: node.label for node in graph.nodes}
    edge = next(
        edge
        for edge in graph.edges
        if (labels[edge.source], labels[edge.target]) == ("A", "B")
    )
    # Two source pairs, two participating objects, three object/pair occurrences.
    assert {metric.name: metric.value for metric in edge.metrics} == {
        "event_pairs": 2,
        "objects": 2,
        "occurrences": 3,
    }


def test_equal_perfect_replay_values_remain_distinct_operators():
    net = ObjectCentricPetriNet(
        (TypedPlace("p", "T"), TypedPlace("q", "T")),
        (Transition("a", "A"),),
        (ObjectArc("p", "a"), ObjectArc("a", "q")),
        ObjectMarking((ObjectToken("p", "x"), ObjectToken("p", "y"))),
        ObjectMarking((ObjectToken("q", "x"), ObjectToken("q", "y"))),
        (("x", "T"), ("y", "T")),
    )
    source = log((("e1", "A", (("x", "flow"),)), ("e2", "A", (("y", "flow"),))))
    spec = ObjectReplaySpec(("T",))
    joint = replay_object_log(source, net, spec)
    flat = replay_flattened_object_log(source, net, spec)
    # Each token moves p->q once. No repair or residual token is needed.
    assert joint.value.token_fitness == flat.value.token_fitness == 1
    assert joint.operator_id != flat.operator_id
    document = loads_visualization(
        dumps_visualization(build_visualization(joint, flat))
    )
    origins = [p for p in document.provenance if p.operator_id]
    assert {p.operator_id for p in origins} == {joint.operator_id, flat.operator_id}
    assert set(origins[0].panel_ids).isdisjoint(origins[1].panel_ids)
    assert not any(f.name == "conformance_verdict" for p in origins for f in p.details)


def test_shared_participation_violation_is_not_overridden_by_flattened_fitness():
    net = ObjectCentricPetriNet(
        (TypedPlace("p", "T"), TypedPlace("q", "T")),
        (Transition("a", "A"),),
        (ObjectArc("p", "a"), ObjectArc("a", "q")),
        ObjectMarking((ObjectToken("p", "x"), ObjectToken("p", "y"))),
        ObjectMarking((ObjectToken("q", "x"), ObjectToken("q", "y"))),
        (("x", "T"), ("y", "T")),
    )
    source = log((("e1", "A", (("x", "flow"), ("y", "flow"))),))
    joint = replay_object_log(source, net, ObjectReplaySpec(("T",)))
    flat = replay_flattened_object_log(source, net, ObjectReplaySpec(("T",)))
    assert joint.status is ComputeStatus.COMPUTED
    assert joint.value.fitting is False
    assert joint.value.log_deviation_count == 1
    assert any(
        step.event_id == "e1"
        and step.deviation_reason == "inadmissible_event_participation"
        for step in joint.value.steps
    )
    assert flat.value.token_fitness == 1
    document = loads_visualization(
        dumps_visualization(build_visualization(joint, flat))
    )
    by_operator = {p.operator_id: p for p in document.provenance if p.operator_id}
    details = {f.name: f.value for f in by_operator[joint.operator_id].details}
    assert details["conformance_verdict"] == "not_fitting"
    assert "separately specified process model" in details["conformance_notice"]
    assert not any(
        f.name == "conformance_verdict" for f in by_operator[flat.operator_id].details
    )


def test_failed_inputs_keep_separate_issue_locations_without_panels():
    values = []
    spec = OCDFGSpec(("T",))
    for operator, code, location in (
        ("review.first", "search_limit", ("events", "e1")),
        ("review.second", "unknown_timestamp", ("events", "e2")),
    ):
        values.append(
            ComputationResult(
                operator_id=operator,
                operator_version="1",
                source_digest=None,
                computation_id=computation_identity(operator, "1", None, spec, ()),
                spec=spec,
                status=ComputeStatus.UNAVAILABLE,
                value=None,
                issues=(ComputeIssue(code, "Unresolved observation", location),),
            )
        )
    document = loads_visualization(dumps_visualization(build_visualization(*values)))
    assert document.panels == ()
    assert document.status == "unsupported"
    assert [p.input_path for p in document.provenance] == [(0,), (1,)]
    for item, code, eid in zip(
        document.provenance,
        ("search_limit", "unknown_timestamp"),
        ("e1", "e2"),
    ):
        details = {field.name: field.value for field in item.details}
        assert json.loads(details["issues_json"]) == [
            {
                "code": code,
                "message": "Unresolved observation",
                "at": ["events", eid],
            }
        ]


def test_projection_receipt_is_validated_scoped_and_roundtripped():
    source = log((("e1", "A", (("x", "flow"), ("y", "flow"))),))
    projection = project_object_cases(source, ObjectCaseProjectionSpec("T"))
    document = build_visualization(projection.case_log, projection=projection)
    restored = loads_visualization(dumps_visualization(document))
    receipt = next(
        p
        for p in restored.provenance
        if any(
            f.name == "role" and f.value == "object_case_projection" for f in p.details
        )
    )
    fields = {f.name: f.value for f in receipt.details}
    assert json.loads(fields["projection_receipt_json"]) == json.loads(
        json.dumps(projection.describe())
    )
    assert json.loads(fields["shared_event_case_groups"]) == [
        sorted(t.id for t in projection.case_log.traces)
    ]
    assert set(receipt.panel_ids) == {p.id for p in restored.panels}
    composed = build_visualization(restored, projection.case_log)
    attached = next(
        p for p in composed.provenance if p.source_digest == receipt.source_digest
    )
    assert all(p.startswith("input-0/") for p in attached.panel_ids)


def test_projection_binding_rejects_mismatch_and_forged_receipt():
    projection = project_object_cases(
        log((("e1", "A", (("x", "flow"),)),)), ObjectCaseProjectionSpec("T")
    )
    other = project_object_cases(
        log((("e2", "B", (("x", "flow"),)),)), ObjectCaseProjectionSpec("T")
    )
    with pytest.raises(ValueError, match="digest"):
        build_visualization(other.case_log, projection=projection)
    with pytest.raises(ValueError, match="source and spec"):
        build_visualization(
            projection.case_log,
            projection=replace(projection, occurrence_source_ids=()),
        )
    with pytest.raises(ValueError, match="one CaseLog"):
        build_visualization(projection.case_log, other.case_log, projection=projection)
    with pytest.raises(TypeError, match="ObjectCaseProjection"):
        build_visualization(projection.case_log, projection={})


def test_projection_attaches_to_native_case_result_without_changing_identity():
    projection = project_object_cases(
        log((("e1", "A", (("x", "flow"), ("y", "flow"))),)),
        ObjectCaseProjectionSpec("T"),
    )
    result = cc.discover_dfg(projection.case_log)
    before = result.computation_id
    plain = build_visualization(result)
    attributed = build_visualization(result, projection=projection)
    assert attributed.panels == plain.panels
    assert result.computation_id == before
    assert attributed.provenance[:-1] == plain.provenance
    assert loads_visualization(dumps_visualization(plain)) == plain
