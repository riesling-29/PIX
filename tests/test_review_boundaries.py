"""Review counterexamples with independent expected populations and identities."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.feature_dataset import LeakageSplitSpec, leakage_safe_split
from pix.case_centric.features import CaseSplit
from pix.case_centric.statistics import CasePerformanceSpec, measure_case_performance
from pix.cli import main
from pix.compute.executions import discover_executions
from pix.contracts.execution import ExecutionSpec
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_log_digest
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    audit_projected_split,
    project_object_cases,
    shared_event_case_groups,
)
from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    canonical_digest,
    import_ocel,
)
from pix.results import result_from_json, result_json_bytes

T = datetime(2026, 9, 20, tzinfo=timezone.utc)


def tasks():
    return OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("Task"), ObjectType("Agent")),
        events=(Event("e1", "A", T), Event("e2", "A", T + timedelta(seconds=1))),
        objects=(Object("t1", "Task"), Object("t2", "Task"), Object("r", "Agent")),
        e2o=(
            E2O("e1", "t1", "work"),
            E2O("e2", "t2", "work"),
            E2O("e1", "r", "actor"),
            E2O("e2", "r", "actor"),
        ),
    )


def test_task_boundary_is_explicit_not_inferred_from_agent_name():
    log = tasks()
    all_objects = discover_executions(log, ExecutionSpec("connected_components")).value
    assert len(all_objects.executions) == 1
    task_only = discover_executions(
        log, ExecutionSpec("connected_components", object_types=("Task",))
    ).value
    assert len(task_only.executions) == 2
    assert task_only.overlapping_event_ids == ()
    for execution in task_only.executions:
        assert len(execution.events) == 1
        assert len(execution.objects) == 1
        assert tuple(o.id for o in execution.boundary_objects) == ("r",)
        assert len(execution.excluded_relations) == 1
    leading = discover_executions(
        log, ExecutionSpec("leading_object_nearest_type", leading_object_type="Task")
    ).value
    assert len(leading.executions) == 2
    assert leading.overlapping_event_ids == ("e1", "e2")
    assert all(len(e.events) == 2 for e in leading.executions)


def test_shared_event_requires_grouping_but_shared_resource_does_not():
    log = tasks()
    p = project_object_cases(log, ObjectCaseProjectionSpec("Task"))
    split = CaseSplit(("t1",), (), ("t2",))
    assert audit_projected_split(p, split, namespace="agent/session") == ()
    assert shared_event_case_groups(p) == ()
    shared = replace(log, e2o=log.e2o + (E2O("e1", "t2", "observe"),))
    p = project_object_cases(shared, ObjectCaseProjectionSpec("Task"))
    assert audit_projected_split(p, split, namespace="agent/session") == (
        ("agent/session", "e1", ("test", "train")),
    )
    assert shared_event_case_groups(p) == (("t1", "t2"),)
    result = leakage_safe_split(
        p.case_log, LeakageSplitSpec(shared_case_groups=shared_event_case_groups(p))
    )
    assert result.status.value == "unavailable"
    assert result.value is None
    extra = replace(shared, objects=shared.objects + (Object("t3", "Task"),))
    p = project_object_cases(extra, ObjectCaseProjectionSpec("Task"))
    result = leakage_safe_split(
        p.case_log, LeakageSplitSpec(shared_case_groups=shared_event_case_groups(p))
    )
    assert result.status.value == "computed"
    assert (
        audit_projected_split(p, result.value.partitions, namespace="agent/session")
        == ()
    )
    assert result_from_json(result_json_bytes(result)) == result


def test_same_instant_duplicate_and_utc_range_are_not_repaired():
    other = T.astimezone(timezone(timedelta(hours=9)))
    with pytest.raises(ValueError, match="duplicates"):
        Object("o", "Task", (ObjectAttr("x", 1, T), ObjectAttr("x", 2, other)))
    obj = Object(
        "o",
        "Task",
        (
            ObjectAttr("x", 1, T),
            ObjectAttr("x", 2, T + timedelta(microseconds=1)),
            ObjectAttr("y", 3, other),
        ),
    )
    assert len(obj.attributes) == 3
    with pytest.raises(OverflowError):
        Object(
            "o",
            "Task",
            (
                ObjectAttr(
                    "x", 1, datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1)))
                ),
            ),
        )


def test_projection_normalizes_time_values_collections_but_retains_source():
    log = tasks()
    log = replace(
        log,
        event_types=(EventType("A", (Attribute("when", ValueType.TIME),)),),
        object_types=(
            ObjectType("Task", (Attribute("when", ValueType.TIME),)),
            ObjectType("Agent"),
        ),
        events=tuple(
            replace(e, attributes=(EventAttr("when", T),)) for e in log.events
        ),
        objects=(Object("t1", "Task", (ObjectAttr("when", T, T),)),) + log.objects[1:],
    )
    offset = T.astimezone(timezone(timedelta(hours=-4)))
    changed = replace(
        log,
        event_types=log.event_types[::-1],
        object_types=log.object_types[::-1],
        e2o=log.e2o[::-1],
        events=tuple(
            replace(
                e,
                time=e.time.astimezone(timezone(timedelta(hours=9))),
                attributes=(EventAttr("when", offset),),
            )
            for e in log.events[::-1]
        ),
        objects=tuple(
            replace(
                o,
                attributes=tuple(
                    ObjectAttr(a.name, offset, offset) for a in o.attributes
                ),
            )
            for o in log.objects[::-1]
        ),
    )
    assert canonical_digest(log) == canonical_digest(changed)
    a, b = [
        project_object_cases(x, ObjectCaseProjectionSpec("Task"))
        for x in (log, changed)
    ]
    assert a.case_log == b.case_log
    assert case_log_digest(a.case_log) == case_log_digest(b.case_log)
    assert b.source is changed
    assert b.describe()["profile"] == "pix.object-case-projection.v2"


def document(time="2026-09-20T00:00:00"):
    return {
        "eventTypes": [{"name": "A", "attributes": []}],
        "objectTypes": [{"name": "Task", "attributes": []}],
        "objects": [{"id": "t", "type": "Task", "attributes": [], "relationships": []}],
        "events": [
            {
                "id": "e",
                "type": "A",
                "time": time,
                "attributes": [],
                "relationships": [{"objectId": "t", "qualifier": "work"}],
            }
        ],
    }


def test_assumptions_are_valid_storage_but_optional_admission_rejects(tmp_path, capsys):
    path = tmp_path / "input.jsonocel"
    path.write_text(json.dumps(document()))
    receipt = import_ocel(path)
    assert receipt.valid
    assert receipt.require_ocel().timezone_info.assumed_utc_count == 1
    assert any(
        t.code == "timezone_assumed_utc" and t.count == 1
        for t in receipt.transformations
    )
    with pytest.raises(ValueError, match="admission rejected"):
        receipt.require_ocel(reject_timezone_assumptions=True)
    sidecar = tmp_path / "receipt.json"
    assert (
        main(
            [
                "dfg",
                str(path),
                "--object-type",
                "Task",
                "--receipt-output",
                str(sidecar),
            ]
        )
        == 0
    )
    evidence = json.loads(sidecar.read_text())
    assert evidence["import"]["transformations"]
    assert (
        evidence["projection"]["canonicalSourceDigest"]
        == receipt.canonical_digest.identifier
    )
    assert (
        result_from_json(json.dumps(evidence["result"]["document"])).status.value
        == "computed"
    )
    capsys.readouterr()
    assert (
        main(
            ["dfg", str(path), "--object-type", "Task", "--reject-timezone-assumptions"]
        )
        == 2
    )
    assert "admission rejected" in capsys.readouterr().err


def test_reader_absolute_history_and_duplicate_rejection(tmp_path):
    data = document("2026-09-20T00:00:00Z")
    data["objectTypes"][0]["attributes"] = [{"name": "status", "type": "string"}]
    data["objects"][0]["attributes"] = [
        {"name": "status", "time": "2026-11-01T01:30:00-04:00", "value": "before"},
        {"name": "status", "time": "2026-11-01T01:30:00-05:00", "value": "after"},
    ]
    path = tmp_path / "history.jsonocel"
    path.write_text(json.dumps(data))
    assert len(import_ocel(path).require_ocel().objects[0].attributes) == 2
    data["objects"][0]["attributes"][1]["time"] = "2026-11-01T05:30:00Z"
    path.write_text(json.dumps(data))
    assert not import_ocel(path).valid


def test_busy_union_is_not_mean_service_duration():
    def event(name):
        return CaseEvent(
            name,
            (
                CaseAttribute("concept:name", "string", "A"),
                CaseAttribute("time:timestamp", "date", T + timedelta(seconds=10)),
                CaseAttribute("start", "date", T),
            ),
        )

    log = CaseLog((CaseTrace("a", (event("a"),)), CaseTrace("b", (event("b"),))))
    result = measure_case_performance(log, CasePerformanceSpec(start_attribute="start"))
    assert result.value.cycle_seconds == 5
    assert result.value.cycle_denominator == 2
    assert dict(result.value.service_summaries)["A"].mean == 10
    assert result_from_json(result_json_bytes(result)) == result
