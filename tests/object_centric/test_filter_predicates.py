"""Typed OCEL predicates: independently computed selections and counterexamples."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.filter_predicates import (
    OCFilterPredicates,
    OCFilterPredicateSpec,
    evaluate_filter_predicates,
)
from pix.object_centric.performance import OCPerformanceSpec, measure_performance
from pix.object_centric.relations import (
    AttributeAsOfSpec,
    OCELScalar,
    object_attributes_as_of,
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
)
from pix.results import read_result, write_result

BASE = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


def integer(value):
    return OCELScalar("integer", integer_value=value)


def string(value):
    return OCELScalar("string", text_value=value)


def fixture():
    return OCEL(
        event_types=(
            EventType("A", (Attribute("v", ValueType.INTEGER),)),
            EventType("B", (Attribute("v", ValueType.BOOLEAN),)),
            EventType("C", (Attribute("v", ValueType.STRING),)),
            EventType(
                "D",
                (Attribute("v", ValueType.TIME), Attribute("start", ValueType.TIME)),
            ),
            EventType("M", (Attribute("v", ValueType.INTEGER),)),
            EventType("U"),
        ),
        object_types=(
            ObjectType("order", (Attribute("state", ValueType.STRING),)),
            ObjectType("item"),
            ObjectType("empty"),
        ),
        events=(
            Event("a", "A", BASE, (EventAttr("v", 1),)),
            Event("b", "B", BASE + timedelta(microseconds=10), (EventAttr("v", True),)),
            Event(
                "c",
                "C",
                BASE + timedelta(microseconds=20),
                (EventAttr("v", BASE.isoformat()),),
            ),
            Event(
                "d",
                "D",
                BASE + timedelta(microseconds=30),
                (
                    EventAttr("v", BASE),
                    EventAttr("start", BASE + timedelta(microseconds=25)),
                ),
            ),
            Event("m", "M", BASE + timedelta(microseconds=40)),
            Event("u", "U", BASE + timedelta(microseconds=50)),
        ),
        objects=(
            Object(
                "o",
                "order",
                (
                    ObjectAttr("state", "before", BASE - timedelta(microseconds=1)),
                    ObjectAttr("state", "after", BASE + timedelta(microseconds=20)),
                ),
            ),
            Object("p", "order"),
            Object("i", "item"),
        ),
        e2o=(
            E2O("a", "o", "flow"),
            E2O("a", "o", "audit"),
            E2O("b", "o", "flow"),
            E2O("c", "o", "audit"),
            E2O("d", "o", "flow"),
            E2O("m", "i", "flow"),
        ),
    )


def attr(**kwargs):
    return OCFilterPredicateSpec("event_attribute", attribute="v", **kwargs)


def life(kind, **kwargs):
    return OCFilterPredicateSpec("object_lifecycle", lifecycle=kind, **kwargs)


@pytest.mark.parametrize(
    "expected,selected",
    [
        (integer(1), ("a",)),
        (OCELScalar("boolean", boolean_value=True), ("b",)),
        (string(BASE.isoformat()), ("c",)),
        (OCELScalar("time", timestamp_value=BASE), ("d",)),
        (OCELScalar("float", float_value=1.0), ()),
    ],
)
def test_equality_is_typed_and_unknown_does_not_equal_null(expected, selected):
    result = evaluate_filter_predicates(fixture(), attr(value=expected))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.selected_event_ids == selected
    assert result.value.selected_object_ids == ()
    assert result.value.selection_unit == "events"
    assert result.value.unknown_event_ids == ("m", "u")
    rows = {d.entity_id: d for d in result.value.decisions}
    assert rows["m"].declared is True
    assert rows["m"].reason == "attribute_absent"
    assert rows["u"].declared is False
    assert rows["u"].reason == "attribute_undeclared"


@pytest.mark.parametrize(
    "positive,unknown,selected",
    [
        (True, "exclude", ("a",)),
        (True, "include", ("a", "m", "u")),
        (False, "exclude", ("b", "c", "d")),
        (False, "include", ("b", "c", "d", "m", "u")),
    ],
)
def test_unknown_policy_is_independent_of_positive_complement(
    positive, unknown, selected
):
    result = evaluate_filter_predicates(
        fixture(), attr(value=integer(1), positive=positive, unknown=unknown)
    )
    assert result.value.selected_event_ids == selected
    assert result.value.unknown_event_ids == ("m", "u")


def test_unknown_error_is_unavailable_without_selection():
    result = evaluate_filter_predicates(
        fixture(), attr(value=integer(1), unknown="error")
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert {issue.at[-1] for issue in result.issues} == {"m", "u"}


@pytest.mark.parametrize(
    "positive,selected", [(True, ("a", "b", "c", "d")), (False, ("m", "u"))]
)
def test_presence_is_known_for_both_missing_and_undeclared(positive, selected):
    result = evaluate_filter_predicates(
        fixture(), attr(comparison="present", positive=positive)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.selected_event_ids == selected
    assert result.value.unknown_event_ids == ()


def test_numeric_range_rejects_bool_and_keeps_large_integer_precision():
    log = fixture()
    huge = 2**60 + 1
    log = replace(
        log,
        events=(replace(log.events[0], attributes=(EventAttr("v", huge),)),)
        + log.events[1:],
    )
    result = evaluate_filter_predicates(
        log,
        attr(comparison="numeric_range", minimum=integer(huge), maximum=integer(huge)),
    )
    assert result.value.selected_event_ids == ("a",)
    assert result.value.unknown_event_ids == ("b", "c", "d", "m", "u")
    miss = evaluate_filter_predicates(
        log, attr(comparison="numeric_range", maximum=integer(huge - 1))
    )
    assert miss.value.selected_event_ids == ()


def test_mixed_numeric_bounds_allow_integer_lower_and_float_upper():
    result = evaluate_filter_predicates(
        fixture(),
        attr(
            comparison="numeric_range",
            minimum=integer(1),
            maximum=OCELScalar("float", float_value=1.5),
        ),
    )
    assert result.value.selected_event_ids == ("a",)


def test_event_population_uses_qualified_object_type_and_empty_selects_none():
    spec = attr(comparison="present", object_types=("order",), qualifiers=("flow",))
    result = evaluate_filter_predicates(fixture(), spec)
    assert tuple(d.entity_id for d in result.value.decisions) == ("a", "b", "d")
    assert result.value.selected_event_ids == ("a", "b", "d")
    assert (
        evaluate_filter_predicates(
            fixture(), replace(spec, qualifiers=())
        ).value.decisions
        == ()
    )
    assert (
        evaluate_filter_predicates(
            fixture(), replace(spec, object_types=())
        ).value.decisions
        == ()
    )
    unknown = evaluate_filter_predicates(
        fixture(), replace(spec, object_types=("missing",))
    )
    assert unknown.status is ComputeStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "at,inclusive,value",
    [
        (BASE, True, "before"),
        (BASE + timedelta(microseconds=20), True, "after"),
        (BASE + timedelta(microseconds=20), False, "before"),
    ],
)
def test_object_asof_boundary_never_reads_future(at, inclusive, value):
    spec = OCFilterPredicateSpec(
        "object_attribute",
        attribute="state",
        value=string(value),
        as_of=at,
        as_of_inclusive=inclusive,
        object_types=("order",),
    )
    result = evaluate_filter_predicates(fixture(), spec)
    assert result.value.selection_unit == "objects"
    assert result.value.selected_object_ids == ("o",)
    assert result.value.unknown_object_ids == ("p",)
    row = result.value.decisions[0]
    assert row.observed == string(value)
    assert row.assigned_at <= at
    parent = object_attributes_as_of(
        fixture(), AttributeAsOfSpec(at, ("o", "p"), ("state",), inclusive)
    )
    assert result.parent_computation_ids == (parent.computation_id,)


def test_object_asof_before_first_assignment_is_unknown_and_qualified_population():
    spec = OCFilterPredicateSpec(
        "object_attribute",
        attribute="state",
        value=string("before"),
        as_of=BASE - timedelta(days=1),
        qualifiers=("flow",),
    )
    result = evaluate_filter_predicates(fixture(), spec)
    assert result.value.unknown_object_ids == ("i", "o")
    assert result.value.selected_object_ids == ()
    assert {d.entity_id for d in result.value.decisions} == {"i", "o"}


def test_fixed_asof_and_timestamp_values_normalize_utc():
    shifted = BASE.astimezone(timezone(timedelta(hours=9)))
    first = attr(value=OCELScalar("time", timestamp_value=BASE))
    second = attr(value=OCELScalar("time", timestamp_value=shifted))
    assert first == second
    assert (
        evaluate_filter_predicates(fixture(), first).computation_id
        == evaluate_filter_predicates(fixture(), second).computation_id
    )
    spec = OCFilterPredicateSpec(
        "object_attribute", attribute="state", value=string("before"), as_of=shifted
    )
    assert spec.as_of.tzinfo is timezone.utc


@pytest.mark.parametrize(
    "kind,activity,selected",
    [
        ("start", "A", ("o",)),
        ("end", "D", ("o",)),
        ("contains", "C", ("o",)),
        ("rework", "A", ()),
    ],
)
def test_lifecycle_modes_deduplicate_e2o_and_keep_empty_objects(
    kind, activity, selected
):
    result = evaluate_filter_predicates(fixture(), life(kind, activity=activity))
    assert result.value.selected_object_ids == selected
    assert len(result.value.decisions) == 3
    if kind in ("start", "end"):
        assert result.value.unknown_object_ids == ("p",)
    else:
        assert result.value.unknown_object_ids == ()


def test_rework_counts_distinct_events_and_qualifier_controls_lifecycle():
    log = fixture()
    log = replace(
        log,
        events=log.events + (Event("a2", "A", BASE + timedelta(microseconds=60)),),
        e2o=log.e2o + (E2O("a2", "o", "audit"),),
    )
    result = evaluate_filter_predicates(log, life("rework", activity="A"))
    assert result.value.selected_object_ids == ("o",)
    row = next(d for d in result.value.decisions if d.entity_id == "o")
    assert row.observed == integer(2)
    assert row.witness_event_ids == ("a", "a2")
    assert (
        evaluate_filter_predicates(
            log, life("rework", activity="A", qualifiers=("flow",))
        ).value.selected_object_ids
        == ()
    )


def test_equal_timestamp_boundaries_are_unknown_even_same_label():
    log = fixture()
    log = replace(
        log,
        events=log.events + (Event("a0", "A", BASE),),
        e2o=log.e2o + (E2O("a0", "o", "flow"),),
    )
    result = evaluate_filter_predicates(
        log, life("start", activity="A", positive=False)
    )
    row = next(d for d in result.value.decisions if d.entity_id == "o")
    assert row.matched is None and not row.selected
    assert row.reason == "ambiguous_lifecycle_boundary"
    assert row.witness_event_ids == ("a", "a0")
    assert "o" in result.value.unknown_object_ids


def test_duration_is_exact_qualified_observed_span_not_source_order():
    log = fixture()
    log = replace(log, events=tuple(reversed(log.events)))
    spec = life(
        "duration",
        comparison="numeric_range",
        minimum=integer(30),
        maximum=integer(30),
        qualifiers=("flow",),
    )
    result = evaluate_filter_predicates(log, spec)
    assert result.value.selected_object_ids == ("o",)
    assert result.value.unknown_object_ids == ("p",)
    rows = {d.entity_id: d for d in result.value.decisions}
    assert rows["o"].observed == integer(30)
    assert rows["o"].witness_event_ids == ("a", "d")
    assert rows["i"].observed == integer(0)


def test_duration_ties_are_zero_span_without_inferring_event_order():
    log = fixture()
    log = replace(log, events=tuple(replace(e, time=BASE) for e in log.events))
    result = evaluate_filter_predicates(log, life("duration", value=integer(0)))
    assert result.value.selected_object_ids == ("i", "o")
    assert result.value.unknown_object_ids == ("p",)


def test_performance_uses_native_parent_and_exact_service_microseconds():
    performance = OCPerformanceSpec(
        metrics=("service",), activities=("D",), start_attribute="start"
    )
    spec = OCFilterPredicateSpec(
        "performance",
        comparison="numeric_range",
        minimum=integer(5),
        maximum=integer(5),
        performance_spec=performance,
    )
    result = evaluate_filter_predicates(fixture(), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.selected_event_ids == ("d",)
    assert result.value.decisions[0].observed == integer(5)
    assert result.parent_computation_ids == (
        measure_performance(fixture(), performance).computation_id,
    )


@pytest.mark.parametrize(
    "metric,expected",
    [
        ("flow", 20),
        ("sojourn", 20),
        ("synchronization", 0),
        ("pooling", 0),
        ("lagging", 0),
        ("readiness", 0),
        ("service", 5),
        ("ready_waiting", 15),
        ("first_input_waiting", 15),
        ("object_frequency", 1),
    ],
)
def test_each_supported_performance_metric_preserves_qualified_sample(metric, expected):
    performance = OCPerformanceSpec(
        metrics=(metric,),
        activities=("D",),
        qualifiers=("flow",),
        object_type="order",
        start_attribute="start",
    )
    result = evaluate_filter_predicates(
        fixture(),
        OCFilterPredicateSpec(
            "performance", value=integer(expected), performance_spec=performance
        ),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.selected_event_ids == ("d",)
    assert result.value.decisions[0].observed == integer(expected)
    assert len(result.value.decisions) == 1


@pytest.mark.parametrize(
    "start,reason",
    [
        (None, "missing_start_timestamp"),
        (BASE + timedelta(microseconds=31), "start_after_completion"),
    ],
)
def test_performance_missing_and_timewarp_are_unknown(start, reason):
    log = fixture()
    event = log.events[3]
    attrs = (
        (event.attributes[0],)
        if start is None
        else (event.attributes[0], EventAttr("start", start))
    )
    log = replace(
        log,
        events=log.events[:3] + (replace(event, attributes=attrs),) + log.events[4:],
    )
    spec = OCFilterPredicateSpec(
        "performance",
        value=integer(0),
        positive=False,
        performance_spec=OCPerformanceSpec(
            metrics=("service",), activities=("D",), start_attribute="start"
        ),
    )
    result = evaluate_filter_predicates(log, spec)
    assert result.value.unknown_event_ids == ("d",)
    assert result.value.selected_event_ids == ()
    assert result.value.decisions[0].reason == reason


def test_performance_ties_are_unknown_not_causal_zero():
    log = fixture()
    log = replace(log, events=tuple(replace(e, time=BASE) for e in log.events))
    spec = OCFilterPredicateSpec(
        "performance",
        value=integer(0),
        performance_spec=OCPerformanceSpec(metrics=("flow",), activities=("D",)),
    )
    result = evaluate_filter_predicates(log, spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any(issue.code == "ambiguous_event_order" for issue in result.issues)
    assert result.parent_computation_ids == (
        measure_performance(log, spec.performance_spec).computation_id,
    )


def test_payload_contains_no_source_log_and_request_identity_tracks_semantics():
    log = fixture()
    spec = attr(value=integer(1))
    result = evaluate_filter_predicates(log, spec)
    same = evaluate_filter_predicates(ComputationContext(log), spec)
    assert result == same
    assert not hasattr(result.value, "log")
    changes = (
        replace(spec, positive=False),
        replace(spec, unknown="include"),
        replace(spec, value=OCELScalar("boolean", boolean_value=True)),
    )
    assert all(
        evaluate_filter_predicates(log, s).computation_id != result.computation_id
        for s in changes
    )
    with pytest.raises(ValueError):
        replace(result.value, selected_event_ids=("u",))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "unknown"},
        {"mode": "event_attribute", "attribute": "v"},
        {"mode": "event_attribute", "attribute": "v", "value": 1},
        {
            "mode": "event_attribute",
            "attribute": "v",
            "comparison": "present",
            "value": integer(1),
        },
        {"mode": "event_attribute", "attribute": "v", "comparison": "numeric_range"},
        {
            "mode": "event_attribute",
            "attribute": "v",
            "comparison": "numeric_range",
            "minimum": integer(2),
            "maximum": integer(1),
        },
        {
            "mode": "event_attribute",
            "attribute": "v",
            "comparison": "numeric_range",
            "minimum": OCELScalar("boolean", boolean_value=True),
        },
        {
            "mode": "event_attribute",
            "attribute": "v",
            "value": integer(1),
            "positive": 1,
        },
        {
            "mode": "event_attribute",
            "attribute": "v",
            "value": integer(1),
            "object_types": ["order"],
        },
        {
            "mode": "event_attribute",
            "attribute": "v",
            "value": integer(1),
            "as_of": BASE,
        },
        {"mode": "object_attribute", "attribute": "state", "value": string("before")},
        {
            "mode": "object_attribute",
            "attribute": "state",
            "value": string("before"),
            "as_of": BASE.replace(tzinfo=None),
        },
        {"mode": "object_lifecycle", "lifecycle": "start"},
        {
            "mode": "object_lifecycle",
            "lifecycle": "start",
            "activity": "A",
            "value": string("A"),
        },
        {"mode": "object_lifecycle", "lifecycle": "duration", "value": integer(-1)},
        {
            "mode": "object_lifecycle",
            "lifecycle": "duration",
            "value": OCELScalar("float", float_value=1.0),
        },
        {"mode": "performance", "value": integer(1)},
        {
            "mode": "performance",
            "value": integer(1),
            "performance_spec": OCPerformanceSpec(
                metrics=("elapsed",), object_type="order"
            ),
        },
        {
            "mode": "performance",
            "value": integer(1),
            "performance_spec": OCPerformanceSpec(metrics=("flow", "service")),
        },
        {
            "mode": "performance",
            "value": integer(1),
            "qualifiers": ("flow",),
            "performance_spec": OCPerformanceSpec(metrics=("flow",)),
        },
    ],
)
def test_request_rejects_ambiguous_and_noncanonical_parameters(kwargs):
    with pytest.raises((TypeError, ValueError)):
        OCFilterPredicateSpec(**kwargs)


def test_null_is_not_a_canonical_scalar_and_invalid_log_has_no_payload():
    with pytest.raises((TypeError, ValueError)):
        OCELScalar("null")
    result = evaluate_filter_predicates(None, attr(value=integer(1)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    with pytest.raises(TypeError):
        evaluate_filter_predicates(fixture(), None)


def test_empty_log_and_explicit_empty_population_are_valid():
    result = evaluate_filter_predicates(OCEL(), attr(comparison="present"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value == OCFilterPredicates("events", (), (), (), (), ())


@pytest.mark.parametrize(
    "spec",
    [
        attr(value=integer(1)),
        attr(value=OCELScalar("boolean", boolean_value=True)),
        attr(value=string(BASE.isoformat())),
        attr(value=OCELScalar("time", timestamp_value=BASE)),
        attr(value=OCELScalar("float", float_value=1.0)),
        attr(comparison="numeric_range", minimum=integer(1)),
        attr(comparison="present", positive=False),
        attr(value=integer(1), unknown="error"),
        OCFilterPredicateSpec(
            "object_attribute", attribute="state", value=string("before"), as_of=BASE
        ),
        life("contains", activity="A"),
        life("duration", comparison="numeric_range", maximum=integer(30)),
        OCFilterPredicateSpec(
            "performance",
            value=integer(5),
            performance_spec=OCPerformanceSpec(
                metrics=("service",), activities=("D",), start_attribute="start"
            ),
        ),
    ],
)
def test_registered_file_roundtrip_preserves_types_parents_and_decisions(
    tmp_path, spec
):
    result = evaluate_filter_predicates(fixture(), spec)
    path = tmp_path / "predicate.json"
    write_result(result, path)
    restored = read_result(path)
    assert restored == result
    assert restored.computation_id == result.computation_id
    assert restored.parent_computation_ids == result.parent_computation_ids
