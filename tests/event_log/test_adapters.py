"""End-to-end native case discovery and explicitly constrained OCEL projection."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pix.compute.discovery import discover_process_tree, process_tree_to_petri_net
from pix.compute.replay import replay_traces
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.discovery import DiscoverySpec
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseConversionError,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseOCELMapping,
    CaseSource,
    CaseTrace,
    case_log_digest,
    case_traces,
    read_xes,
    to_ocel,
)
from pix.ocel.validate import validate
from pix.results import result_from_json, result_json_bytes

TIME = datetime(2024, 1, 1, tzinfo=timezone.utc)


def event(id_, activity="A", *, time=TIME, extra=()):
    return CaseEvent(
        id_,
        (
            *(
                (CaseAttribute("concept:name", "string", activity),)
                if activity is not None
                else ()
            ),
            *(
                (CaseAttribute("time:timestamp", "date", time),)
                if time is not None
                else ()
            ),
            *extra,
        ),
    )


def test_xes_without_timestamps_feeds_discovery_replay_and_result_roundtrip(tmp_path):
    path = tmp_path / "untimed.xes"
    path.write_text("""<log><trace><event><string key="concept:name" value="B"/></event>
       <event><string key="concept:name" value="A"/></event></trace><trace/></log>""")
    log = read_xes(path)
    traces = case_traces(log)
    assert traces.status is ComputeStatus.COMPUTED
    assert traces.operator_id == "pix.case_traces"
    assert [e.activity for e in traces.value.traces[0].events] == ["B", "A"]
    assert all(e.time is None for e in traces.value.traces[0].events)
    assert traces.value.traces[1].events == ()
    assert traces.source_digest == case_log_digest(log)
    assert [issue.code for issue in traces.issues].count("unknown_timestamp") == 2
    assert result_from_json(result_json_bytes(traces)) == traces
    discovered = discover_process_tree(traces, DiscoverySpec(algorithm="pix.im.v1"))
    assert discovered.status is ComputeStatus.COMPUTED
    replay = replay_traces(traces, process_tree_to_petri_net(discovered.value))
    assert replay.status is ComputeStatus.COMPUTED
    assert (
        replay.value.completed_counts.missing
        == replay.value.completed_counts.remaining
        == 0
    )


def test_order_retains_decreasing_timestamps_and_ties():
    late = datetime(2024, 1, 2, tzinfo=timezone.utc)
    log = CaseLog(
        (
            CaseTrace(
                "t", (event("z", "B", time=late), event("a", "A"), event("c", "C"))
            ),
        )
    )
    traces = case_traces(log).value
    assert [e.event_id for e in traces.traces[0].events] == ["z", "a", "c"]
    assert traces.traces[0].events[1].time == traces.traces[0].events[2].time


def test_default_activity_and_explicit_mapping():
    log = CaseLog(
        (
            CaseTrace(
                "t", (CaseEvent("e", (CaseAttribute("task", "string", "Selected"),)),)
            ),
        ),
        globals=(
            CaseGlobal("event", (CaseAttribute("concept:name", "string", "Default"),)),
        ),
    )
    assert case_traces(log).value.traces[0].events[0].activity == "Default"
    spec = CaseTraceSpec(activity_key="task", object_type="request")
    traces = case_traces(log, spec)
    assert traces.value.object_type == "request"
    assert traces.value.traces[0].events[0].activity == "Selected"
    assert traces.computation_id != case_traces(log).computation_id


def test_classifier_identity_cannot_collide_by_delimiter_or_type():
    classifier = CaseClassifier("Both", ("left", "right"))

    def attributes(left, right):
        return (
            CaseAttribute("left", "string", left),
            CaseAttribute("right", "string", right),
        )

    log = CaseLog(
        (
            CaseTrace(
                "t",
                (
                    CaseEvent("e1", attributes("a+b", "c")),
                    CaseEvent("e2", attributes("a", "b+c")),
                ),
            ),
        ),
        classifiers=(classifier,),
    )
    traces = case_traces(log, CaseTraceSpec(classifier="Both"))
    assert traces.status is ComputeStatus.COMPUTED
    assert len({e.activity for e in traces.value.traces[0].events}) == 2
    assert case_traces(log).status is ComputeStatus.UNAVAILABLE
    assert (
        case_traces(log, CaseTraceSpec(classifier="missing")).status
        is ComputeStatus.UNAVAILABLE
    )
    assert (
        case_traces(CaseLog(), CaseTraceSpec(classifier="missing")).status
        is ComputeStatus.UNAVAILABLE
    )


def test_ambiguous_activity_unavailable_and_naive_time_unknown():
    log = CaseLog((CaseTrace("t", (event("e", time=datetime(2024, 1, 1)),)),))
    assert case_traces(log).value.traces[0].events[0].time is None
    attrs = (CaseAttribute("concept:name", "string", "B"),)
    duplicate = CaseLog((CaseTrace("t", (event("e", extra=attrs),)),))
    assert case_traces(duplicate).status is ComputeStatus.UNAVAILABLE


def test_selected_primitive_activity_keeps_nested_metadata_in_native_source():
    activity = CaseAttribute(
        "concept:name",
        "string",
        "A",
        children=(CaseAttribute("language", "string", "en"),),
    )
    log = CaseLog((CaseTrace("t", (CaseEvent("e", (activity,)),)),))
    assert case_traces(log).value.traces[0].events[0].activity == "A"
    assert log.traces[0].events[0].attributes[0].children[0].value == "en"


def test_digest_covers_nested_metadata_order_lexical_and_ignores_path():
    log = CaseLog(
        (CaseTrace("t", (event("e1"), event("e2", "B"))),),
        attributes=(
            CaseAttribute(
                "list", "list", values=(CaseAttribute("x", "int", 2, lexical="02"),)
            ),
        ),
    )
    digest = case_log_digest(log)
    source = CaseSource("left.xes", "xes", "a" * 64, 1)
    assert digest == case_log_digest(replace(log, source=source))
    reordered = replace(
        log,
        traces=(replace(log.traces[0], events=tuple(reversed(log.traces[0].events))),),
    )
    assert digest != case_log_digest(reordered)
    nested = replace(
        log,
        attributes=(
            CaseAttribute(
                "list", "list", values=(CaseAttribute("x", "int", 2, lexical="2"),)
            ),
        ),
    )
    assert digest != case_log_digest(nested)


def test_explicit_ocel_conversion_keeps_empty_cases_attributes_and_provenance():
    attrs = (
        CaseAttribute("concept:name", "string", "same name"),
        CaseAttribute("amount", "int", 10),
    )
    log = CaseLog(
        (
            CaseTrace(
                "t1",
                (event("e", extra=(CaseAttribute("identity:id", "id", "source-id"),)),),
                attrs,
            ),
            CaseTrace("t2", (), attrs),
        ),
        attributes=(
            CaseAttribute(
                "meta",
                "container",
                children=(CaseAttribute("source", "string", "nested log metadata"),),
            ),
        ),
        globals=(
            CaseGlobal(
                "event", (CaseAttribute("lifecycle:transition", "string", "complete"),)
            ),
        ),
        metadata=(("creator", "fixture"),),
    )
    converted = to_ocel(
        log, CaseOCELMapping(case_object_type="ticket", qualifier="contains")
    )
    assert converted.valid
    ocel = converted.require_ocel()
    assert validate(ocel).valid
    assert converted.source_log is log and converted.source_digest == case_log_digest(
        log
    )
    assert {obj.id for obj in ocel.objects} == {"t1", "t2"}
    assert ocel.e2o[0].object == "t1" and ocel.e2o[0].qualifier == "contains"
    assert (
        dict((a.name, a.value) for a in ocel.events[0].attributes)[
            "lifecycle:transition"
        ]
        == "complete"
    )
    assert len(ocel.objects[1].attributes) == 2
    assert "native_provenance_sidecar" in {t.code for t in converted.transformations}
    assert ocel.objects[0].attributes[0].time == datetime(
        1970, 1, 1, tzinfo=timezone.utc
    )


@pytest.mark.parametrize(
    "extra",
    [
        (CaseAttribute("nested", "list", values=(CaseAttribute("x", "string", "v"),)),),
        (CaseAttribute("nested", "container"),),
        (CaseAttribute("null", "null"),),
        (CaseAttribute("float", "float", float("inf")),),
        (
            CaseAttribute(
                "child",
                "string",
                "v",
                children=(CaseAttribute("lang", "string", "en"),),
            ),
        ),
        (CaseAttribute("date", "date", datetime(2024, 1, 1)),),
    ],
)
def test_conversion_rejects_nonprimitive_or_unrepresentable_event_attributes(extra):
    log = CaseLog((CaseTrace("t", (event("e", extra=extra),)),))
    converted = to_ocel(log)
    assert not converted.valid and converted.ocel is None
    assert converted.issues[0].at == ("trace", "t", "event", "e")
    assert converted.source_log is log
    with pytest.raises(CaseConversionError) as error:
        converted.require_ocel()
    assert error.value.result is converted


@pytest.mark.parametrize(
    "time,activity", [(None, "A"), (TIME, None), (datetime(2024, 1, 1), "A")]
)
def test_conversion_never_invents_missing_event_facts(time, activity):
    log = CaseLog((CaseTrace("t", (event("e", activity, time=time),)),))
    assert not to_ocel(log).valid


def test_conversion_conflicting_types_are_explicit_failure():
    log = CaseLog(
        (
            CaseTrace(
                "t",
                (
                    event("a", extra=(CaseAttribute("amount", "int", 1),)),
                    event("b", extra=(CaseAttribute("amount", "string", "one"),)),
                ),
            ),
        )
    )
    result = to_ocel(log)
    assert not result.valid and "conflicting" in result.issues[0].message


def test_conversion_nested_trace_attr_fails_and_empty_log_is_explicit():
    log = CaseLog(
        (CaseTrace("empty", attributes=(CaseAttribute("nested", "container"),)),)
    )
    assert not to_ocel(log).valid
    assert to_ocel(CaseLog()).valid
    assert case_traces(CaseLog()).value.traces == ()
