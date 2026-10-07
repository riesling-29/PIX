"""Hand-counted OCEL projection and temporal-history boundary examples."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.filtering import (
    OCELFilterSpec,
    filter_ocel,
    materialize_sublog,
)
from pix.ocel import (
    E2O,
    O2O,
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
    validate,
)
from pix.ocel.metadata import OCELImportInfo, TimezoneInfo


def day(value):
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=value)


def example():
    return OCEL(
        event_types=(
            EventType("A"),
            EventType("B"),
            EventType("C"),
            EventType("orphan"),
        ),
        object_types=(
            ObjectType(
                "order",
                (
                    Attribute("stage", ValueType.STRING),
                    Attribute("amount", ValueType.INTEGER),
                    Attribute("future", ValueType.STRING),
                ),
            ),
            ObjectType("parcel"),
            ObjectType("unused"),
        ),
        events=(
            Event("e1", "A", day(1)),
            Event("e2", "B", day(3)),
            Event("e3", "C", day(5)),
            Event("e4", "B", day(7)),
            Event("orphan", "orphan", day(4)),
        ),
        objects=(
            Object(
                "a",
                "order",
                (
                    ObjectAttr("stage", "new", day(0)),
                    ObjectAttr("stage", "queued", day(1)),
                    ObjectAttr("stage", "running", day(3)),
                    ObjectAttr("stage", "done", day(7)),
                    ObjectAttr("amount", 10, day(2)),
                    ObjectAttr("amount", 20, day(5)),
                    ObjectAttr("future", "not-yet", day(8)),
                ),
            ),
            Object("b", "parcel"),
            Object("c", "parcel"),
            Object("d", "order"),
            Object("isolated", "unused"),
        ),
        e2o=(
            E2O("e1", "a", ""),
            E2O("e2", "a", "input"),
            E2O("e2", "a", "audit"),
            E2O("e2", "b", "output"),
            E2O("e3", "c", ""),
            E2O("e4", "d", ""),
        ),
        o2o=(
            O2O("a", "b", "produces"),
            O2O("b", "c", "next"),
            O2O("d", "a", "parent"),
            O2O("c", "c", "self"),
        ),
        import_info=OCELImportInfo(
            "fixture", "ocel-json", "fixture-digest", TimezoneInfo()
        ),
    )


def value(spec=OCELFilterSpec(), source=None):
    source = example() if source is None else source
    result = filter_ocel(source, spec)
    assert result.status is ComputeStatus.COMPUTED
    log = materialize_sublog(source, result)
    assert validate(log).valid
    return SimpleNamespace(
        log=log,
        **{
            field.name: getattr(result.value, field.name)
            for field in fields(result.value)
        },
    )


def as_of(obj, time):
    # Independent query: sort all eligible facts by time, then take last per key.
    found = {}
    for fact in sorted(obj.attributes, key=lambda row: row.time):
        if fact.time <= time:
            found[fact.name] = fact.value
    return found


def test_default_is_canonical_identity_and_preserves_orphans_schema_metadata():
    source = example()
    actual = value(source=source)
    assert canonical_digest(actual.log) == canonical_digest(source)
    assert actual.log.import_info == source.import_info
    assert actual.selected_event_ids == ("e1", "e2", "e3", "e4", "orphan")
    assert actual.selected_object_ids == ("a", "b", "c", "d", "isolated")
    assert actual.dropped_event_ids == actual.dropped_object_ids == ()
    assert (
        actual.history_assignments_removed
        == actual.dropped_e2o_count
        == actual.dropped_o2o_count
        == 0
    )


@pytest.mark.parametrize(
    "policy,events",
    [
        ("any", ("e1", "e2")),
        ("all", ("e1",)),
        ("retain", ("e1", "e2", "e3", "e4", "orphan")),
    ],
)
def test_object_selection_projects_shared_event_with_explicit_any_all_retain(
    policy, events
):
    actual = value(OCELFilterSpec(object_ids=("a",), object_event_policy=policy))
    assert actual.selected_event_ids == events
    assert actual.selected_object_ids == ("a",)
    assert actual.log.o2o == ()
    assert {relation.object for relation in actual.log.e2o} == {"a"}
    if policy != "all":
        assert {r.qualifier for r in actual.log.e2o if r.event == "e2"} == {
            "input",
            "audit",
        }


def test_event_and_activity_predicates_are_intersection_not_union():
    actual = value(
        OCELFilterSpec(
            event_ids=("e1", "e2", "e3"), activities=("B",), isolated_objects="drop"
        )
    )
    assert actual.selected_event_ids == ("e2",)
    assert actual.selected_object_ids == ("a", "b")
    assert len(actual.log.e2o) == 3
    assert actual.log.o2o == (O2O("a", "b", "produces"),)
    assert actual.dropped_e2o_count == 3
    assert actual.dropped_o2o_count == 3


def test_object_ids_and_types_intersect_before_explicit_cross_type_expansion():
    empty = value(OCELFilterSpec(object_ids=("a",), object_types=("parcel",)))
    assert empty.selected_object_ids == empty.selected_event_ids == ()
    expanded = value(
        OCELFilterSpec(
            object_ids=("a",),
            object_types=("order",),
            o2o_depth=1,
            o2o_direction="outbound",
        )
    )
    assert expanded.seed_object_ids == ("a",)
    assert expanded.closure_added_object_ids == ("b",)
    assert expanded.selected_object_ids == ("a", "b")


@pytest.mark.parametrize(
    "direction,depth,expected",
    [
        ("outbound", 0, ("a",)),
        ("outbound", 1, ("a", "b")),
        ("outbound", 2, ("a", "b", "c")),
        ("outbound", 999999, ("a", "b", "c")),
        ("inbound", 1, ("a", "d")),
        ("inbound", 3, ("a", "d")),
        ("both", 1, ("a", "b", "d")),
        ("both", 2, ("a", "b", "c", "d")),
    ],
)
def test_o2o_closure_hop_count_direction_and_self_loop_termination(
    direction, depth, expected
):
    actual = value(
        OCELFilterSpec(object_ids=("a",), o2o_depth=depth, o2o_direction=direction)
    )
    assert actual.selected_object_ids == expected
    assert all(
        edge.source in expected and edge.target in expected for edge in actual.log.o2o
    )


def test_expansion_does_not_expand_explicit_event_selection():
    actual = value(
        OCELFilterSpec(
            event_ids=("e1",), object_ids=("a",), o2o_depth=2, o2o_direction="outbound"
        )
    )
    assert actual.selected_object_ids == ("a", "b", "c")
    assert actual.selected_event_ids == ("e1",)
    dropped = value(
        OCELFilterSpec(
            event_ids=("e1",),
            object_ids=("a",),
            o2o_depth=2,
            o2o_direction="outbound",
            isolated_objects="drop",
        )
    )
    assert dropped.selected_object_ids == ("a",)
    assert dropped.closure_added_object_ids == ("b", "c")
    assert dropped.log.o2o == ()


def test_closed_timestamp_window_does_not_require_related_events():
    actual = value(OCELFilterSpec(start=day(3), end=day(5)))
    assert actual.selected_event_ids == ("e2", "e3", "orphan")
    single_instant = value(OCELFilterSpec(start=day(3), end=day(3)))
    assert single_instant.selected_event_ids == ("e2",)


def test_history_boundary_keeps_last_prior_per_attribute_and_no_future_values():
    source = example()
    actual = value(OCELFilterSpec(start=day(4), end=day(6)), source)
    facts = actual.log.get_object("a").attributes
    assert facts == (
        ObjectAttr("amount", 10, day(2)),
        ObjectAttr("amount", 20, day(5)),
        ObjectAttr("stage", "running", day(3)),
    )
    assert actual.history_assignments_removed == 4
    for time in (day(4), day(5), day(6), day(5) + timedelta(seconds=1)):
        assert as_of(actual.log.get_object("a"), time) == as_of(
            source.get_object("a"), time
        )
    assert "future" not in as_of(actual.log.get_object("a"), day(6))


def test_history_assignment_at_start_is_retained_with_original_timestamp():
    actual = value(OCELFilterSpec(start=day(3), end=day(5)))
    facts = actual.log.get_object("a").attributes
    assert ObjectAttr("stage", "queued", day(1)) in facts
    assert ObjectAttr("stage", "running", day(3)) in facts
    assert ObjectAttr("amount", 20, day(5)) in facts
    assert ObjectAttr("stage", "done", day(7)) not in facts


@pytest.mark.parametrize(
    "start,end", [(None, day(3)), (day(3), None), (day(3), day(5))]
)
def test_full_history_policy_is_independent_of_event_window(start, end):
    source = example()
    actual = value(
        OCELFilterSpec(start=start, end=end, history_policy="preserve_all"), source
    )
    assert set(actual.log.get_object("a").attributes) == set(
        source.get_object("a").attributes
    )
    assert actual.history_assignments_removed == 0


def test_history_one_sided_bounds():
    start_only = value(OCELFilterSpec(start=day(4)))
    assert len(start_only.log.get_object("a").attributes) == 5
    end_only = value(OCELFilterSpec(end=day(3)))
    assert len(end_only.log.get_object("a").attributes) == 4


def test_empty_selections_and_declared_but_unused_type_are_valid():
    for spec in (
        OCELFilterSpec(object_ids=()),
        OCELFilterSpec(event_ids=(), isolated_objects="drop"),
        OCELFilterSpec(activities=(), isolated_objects="drop"),
    ):
        actual = value(spec)
        assert (
            actual.log.events
            == actual.log.objects
            == actual.log.e2o
            == actual.log.o2o
            == ()
        )
        assert actual.log.event_types and actual.log.object_types
    unused = value(OCELFilterSpec(object_types=("unused",)))
    assert unused.selected_event_ids == ()
    assert unused.selected_object_ids == ("isolated",)
    empty = value(source=OCEL())
    assert empty.log == OCEL()


@pytest.mark.parametrize(
    "field,code",
    [
        ("event_ids", "unknown_event_id"),
        ("activities", "unknown_activity"),
        ("object_ids", "unknown_object_id"),
        ("object_types", "unknown_object_type"),
    ],
)
def test_unknown_selections_are_unavailable_not_an_empty_computation(field, code):
    result = filter_ocel(example(), OCELFilterSpec(**{field: ("missing",)}))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == code


def test_invalid_ocel_returns_invalid_input_with_evidence():
    invalid = replace(example(), e2o=(E2O("missing", "a", ""),))
    result = filter_ocel(invalid)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None and result.issues
    assert filter_ocel("not an OCEL").status is ComputeStatus.INVALID_INPUT


def test_input_spec_payload_immutable_and_context_identity_equivalent():
    source = example()
    before = canonical_digest(source)
    spec = OCELFilterSpec(object_ids=("b", "a", "a"), start=day(3))
    actual = filter_ocel(source, spec)
    repeated = filter_ocel(ComputationContext(source), spec)
    assert actual == repeated
    assert canonical_digest(source) == before
    assert spec.object_ids == ("a", "b")
    with pytest.raises(FrozenInstanceError):
        spec.o2o_depth = 2
    with pytest.raises(FrozenInstanceError):
        actual.value.selected_event_ids = ()
    projected = materialize_sublog(source, actual)
    with pytest.raises(FrozenInstanceError):
        projected.objects[0].attributes = ()


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"event_ids": ["a"]}, TypeError),
        ({"activities": ("",)}, ValueError),
        ({"object_types": (1,)}, TypeError),
        ({"o2o_depth": True}, TypeError),
        ({"o2o_depth": -1}, ValueError),
        ({"o2o_depth": 1.5}, TypeError),
        ({"o2o_direction": "sideways"}, ValueError),
        ({"object_event_policy": "sometimes"}, ValueError),
        ({"isolated_objects": "guess"}, ValueError),
        ({"history_policy": "truncate"}, ValueError),
        ({"start": datetime(2026, 1, 1)}, ValueError),
        ({"start": "2026-01-01"}, TypeError),
        ({"start": day(5), "end": day(3)}, ValueError),
    ],
)
def test_bad_spec_is_rejected(kwargs, error):
    with pytest.raises(error):
        OCELFilterSpec(**kwargs)


def test_timezones_normalize_and_equivalent_specs_share_identity():
    shifted = day(3).astimezone(timezone(timedelta(hours=9)))
    one = filter_ocel(example(), OCELFilterSpec(start=shifted))
    two = filter_ocel(example(), OCELFilterSpec(start=day(3)))
    assert one == two


def test_persisted_payload_rejects_broken_selection_evidence():
    actual = filter_ocel(example()).value
    with pytest.raises(ValueError, match="disjoint"):
        replace(actual, dropped_object_ids=("a",))
    with pytest.raises(ValueError, match="seed"):
        replace(actual, closure_added_object_ids=("a",))


def test_result_round_trip_uses_explicit_schema_with_import_metadata():
    from pix import results

    actual = filter_ocel(example(), OCELFilterSpec(start=day(3), end=day(5)))
    restored = results.result_from_json(results.result_json_bytes(actual))
    assert restored == actual
    restored_log = materialize_sublog(example(), restored)
    assert restored_log == materialize_sublog(example(), actual)
    assert restored_log.import_info == example().import_info


def test_time_attribute_projection_remains_typed_and_canonical():
    from pix import results

    source = OCEL(
        event_types=(EventType("A", (Attribute("scheduled", ValueType.TIME),)),),
        object_types=(ObjectType("order", (Attribute("due", ValueType.TIME),)),),
        events=(Event("e", "A", day(3), (EventAttr("scheduled", day(4)),)),),
        objects=(Object("o", "order", (ObjectAttr("due", day(5), day(0)),)),),
        e2o=(E2O("e", "o", ""),),
    )
    actual = value(OCELFilterSpec(start=day(3), end=day(3)), source)
    assert actual.log.events[0].attributes[0].value == day(4)
    assert actual.log.objects[0].attributes[0].value == day(5)
    result = filter_ocel(source, OCELFilterSpec(start=day(3), end=day(3)))
    restored = results.result_from_json(results.result_json_bytes(result))
    assert restored == result
    restored_log = materialize_sublog(source, restored)
    assert validate(restored_log).valid
    assert restored_log.events[0].attributes[0].value == day(4)
    assert restored_log.objects[0].attributes[0].value == day(5)
    assert restored_log == actual.log


def test_materialization_rejects_other_sources_and_invalid_sources():
    source = example()
    result = filter_ocel(source)
    other = replace(source, o2o=())
    with pytest.raises(ValueError, match="source digest"):
        materialize_sublog(other, result)
    invalid = replace(source, e2o=(E2O("missing", "a", ""),))
    with pytest.raises(ValueError, match="invalid source"):
        materialize_sublog(invalid, result)
    with pytest.raises(TypeError):
        materialize_sublog(source, "not a result")
    unavailable = filter_ocel(source, OCELFilterSpec(object_ids=("missing",)))
    with pytest.raises(ValueError, match="computed OCEL filter"):
        materialize_sublog(source, unavailable)


def test_materialization_rechecks_identity_and_selection_evidence():
    source = example()
    result = filter_ocel(source)
    for changed in (
        replace(result, computation_id="tampered"),
        replace(result, spec=OCELFilterSpec(activities=("A",))),
        replace(result, operator_version="2.0.0"),
        replace(result, parent_computation_ids=("fake-parent",)),
        replace(result, value=replace(result.value, dropped_e2o_count=99)),
        replace(result, value=replace(result.value, selected_event_ids=())),
    ):
        with pytest.raises(ValueError, match="identity or selection evidence"):
            materialize_sublog(source, changed)
    wrong_operator = replace(result, operator_id="pix.some_other_operator")
    with pytest.raises(ValueError, match="computed OCEL filter"):
        materialize_sublog(source, wrong_operator)


def test_materialization_accepts_canonical_equivalent_context_and_typed_values():
    source = example()
    result = filter_ocel(source, OCELFilterSpec(object_ids=("a",)))
    reordered = replace(
        source,
        events=tuple(reversed(source.events)),
        objects=tuple(reversed(source.objects)),
    )
    assert materialize_sublog(
        ComputationContext(reordered), result
    ) == materialize_sublog(source, result)
