"""Hand-counted OCEL census and independent exhaustive participation oracle."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.statistics import ObjectStatisticsSpec, object_statistics
from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def example():
    """A has degree samples (3,1,1) on both sides; B has (2) and (1,1)."""
    return OCEL(
        event_types=(EventType("A"), EventType("B"), EventType("U")),
        object_types=(ObjectType("order"), ObjectType("parcel"), ObjectType("unused")),
        events=(
            Event("a1", "A", ORIGIN),
            Event("a2", "A", ORIGIN),
            Event("a3", "A", ORIGIN + timedelta(microseconds=1)),
            Event("b1", "B", ORIGIN + timedelta(microseconds=2)),
            Event("b2", "B", ORIGIN + timedelta(microseconds=2)),
            Event("unlinked", "U", ORIGIN + timedelta(microseconds=3)),
        ),
        objects=(
            Object("o1", "order"),
            Object("o2", "order"),
            Object("o3", "order"),
            Object("isolated", "order"),
            Object("p1", "parcel"),
        ),
        e2o=(
            E2O("a1", "o1", "flow"),
            E2O("a2", "o1", "flow"),
            E2O("a3", "o1", "flow"),
            E2O("a1", "o2", "flow"),
            E2O("a1", "o3", "flow"),
            E2O("a1", "o1", "audit"),
            E2O("b1", "p1", "flow"),
            E2O("b2", "p1", "flow"),
        ),
        o2o=(O2O("isolated", "o1", "related"),),
    )


def test_hand_counted_population_and_distinct_count_units():
    result = object_statistics(example())
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    assert (
        value.source_event_count,
        value.object_count,
        value.participating_object_count,
        value.participating_event_count,
        value.unique_participation_count,
        value.e2o_relation_count,
    ) == (6, 5, 4, 5, 7, 8)
    assert value.isolated_object_ids == ("isolated",)
    assert value.qualifier_relation_counts == (("audit", 1), ("flow", 7))
    activities = {row.activity: row for row in value.activities}
    assert (
        activities["A"].source_event_count,
        activities["A"].participating_event_count,
        activities["A"].participating_object_count,
        activities["A"].unique_participation_count,
        activities["A"].e2o_relation_count,
    ) == (3, 3, 3, 5, 6)
    assert (
        activities["U"].source_event_count,
        activities["U"].participating_event_count,
        activities["U"].participating_object_count,
    ) == (1, 0, 0)
    order = next(row for row in value.object_types if row.object_type == "order")
    assert order.events_per_object.histogram == ((0, 1), (1, 2), (3, 1))
    assert (order.events_per_object.total, order.events_per_object.sample_count) == (
        5,
        4,
    )
    assert order.lifecycle_duration_microseconds.histogram == ((0, 2), (1, 1))


def test_lifecycle_retains_tied_endpoints_without_inventing_sequence():
    rows = {row.object_id: row for row in object_statistics(example()).value.objects}
    assert rows["o1"].event_ids == ("a1", "a2", "a3")
    assert rows["o1"].first_event_ids == ("a1", "a2")
    assert rows["o1"].last_event_ids == ("a3",)
    assert rows["o1"].duration_microseconds == 1
    assert rows["p1"].first_event_ids == rows["p1"].last_event_ids == ("b1", "b2")
    assert rows["p1"].duration_microseconds == 0
    assert rows["isolated"].event_count == 0
    assert rows["isolated"].first_time is rows["isolated"].last_time is None
    assert rows["isolated"].duration_microseconds is None
    assert rows["isolated"].first_event_ids == rows["isolated"].last_event_ids == ()


def test_median_diagnostics_do_not_mean_any_multiple_participation():
    rows = {
        (row.activity, row.object_type): row
        for row in object_statistics(example()).value.activity_object_types
    }
    a = rows[("A", "order")]
    assert a.events_per_object_counts == (("o1", 3), ("o2", 1), ("o3", 1))
    assert a.objects_per_event_counts == (("a1", 3), ("a2", 1), ("a3", 1))
    assert (
        a.events_per_object.histogram
        == a.objects_per_event.histogram
        == ((1, 2), (3, 1))
    )
    assert not a.divergence_median_gt_one and not a.convergence_median_gt_one
    assert a.any_object_repeats_activity and a.any_event_has_multiple_same_type_objects
    b = rows[("B", "parcel")]
    assert b.divergence_median_gt_one and not b.convergence_median_gt_one
    assert b.events_per_object.median_numerator == 2


def test_even_sample_exact_median_triggers_at_three_halves():
    base = example()
    log = replace(
        base,
        e2o=(E2O("a1", "o1", "flow"), E2O("a1", "o2", "flow"), E2O("a2", "o1", "flow")),
    )
    (row,) = object_statistics(log).value.activity_object_types
    assert (
        row.events_per_object.median_numerator,
        row.events_per_object.median_denominator,
    ) == (3, 2)
    assert (
        row.objects_per_event.median_numerator,
        row.objects_per_event.median_denominator,
    ) == (3, 2)
    assert row.divergence_median_gt_one and row.convergence_median_gt_one


def test_multiple_roles_do_not_inflate_unique_samples_but_remain_counted():
    base = example()
    single = replace(base, e2o=(E2O("a1", "o1", "flow"),))
    multiple = replace(single, e2o=single.e2o + (E2O("a1", "o1", "audit"),))
    before, after = (object_statistics(log).value for log in (single, multiple))
    assert before.unique_participation_count == after.unique_participation_count == 1
    assert (before.e2o_relation_count, after.e2o_relation_count) == (1, 2)
    (a,) = after.activity_object_types
    assert not a.divergence_median_gt_one and not a.convergence_median_gt_one
    assert (
        not a.any_object_repeats_activity
        and not a.any_event_has_multiple_same_type_objects
    )


def test_qualifier_selection_recounts_lifecycles_and_preserves_isolates():
    value = object_statistics(
        example(), ObjectStatisticsSpec(qualifiers=("audit",))
    ).value
    assert value.unique_participation_count == value.e2o_relation_count == 1
    assert value.isolated_object_ids == ("isolated", "o2", "o3", "p1")
    assert (
        next(
            row for row in value.objects if row.object_id == "o1"
        ).duration_microseconds
        == 0
    )
    none = object_statistics(example(), ObjectStatisticsSpec(qualifiers=())).value
    assert none.object_count == 5
    assert (
        none.participating_event_count
        == none.unique_participation_count
        == none.e2o_relation_count
        == 0
    )
    assert none.activity_object_types == ()
    assert all(row.duration_microseconds is None for row in none.objects)


def test_empty_qualifier_is_a_real_qualifier_and_differs_from_empty_selection():
    log = replace(example(), e2o=(E2O("a1", "o1", ""), E2O("a2", "o1", "flow")))
    value = object_statistics(log, ObjectStatisticsSpec(qualifiers=("",))).value
    assert value.qualifier_relation_counts == (("", 1),)
    assert value.participating_event_count == 1


def test_type_selection_empty_declarations_and_unknown_type():
    value = object_statistics(
        example(), ObjectStatisticsSpec(("unused", "parcel"))
    ).value
    assert value.object_count == 1
    assert [row.object_type for row in value.object_types] == ["parcel", "unused"]
    unused = value.object_types[1]
    assert unused.object_count == 0
    assert (
        unused.events_per_object.sample_count
        == unused.events_per_object.median_denominator
        == 0
    )
    assert unused.events_per_object.median_numerator is None
    assert (
        object_statistics(example(), ObjectStatisticsSpec(())).value.object_count == 0
    )
    failure = object_statistics(example(), ObjectStatisticsSpec(("order", "unknown")))
    assert failure.status is ComputeStatus.UNAVAILABLE and failure.value is None
    assert failure.issues[0].code == "unknown_object_type"


def test_empty_log_and_unlinked_event_census():
    empty = OCEL((), (), (), (), (), ())
    result = object_statistics(empty)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.source_event_count == result.value.object_count == 0
    assert result.value.activities == result.value.activity_object_types == ()
    assert result.value.objects == result.value.object_types == ()


def test_global_input_validation_and_wrong_spec_type():
    result = object_statistics("not a log")
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.source_digest is result.computation_id is None
    dangling = replace(example(), e2o=(E2O("a1", "missing", "flow"),))
    assert object_statistics(dangling).status is ComputeStatus.INVALID_INPUT
    with pytest.raises(TypeError):
        object_statistics(example(), ())


@pytest.mark.parametrize(
    "kwargs, exception",
    [
        ({"object_types": ["order"]}, TypeError),
        ({"object_types": (1,)}, TypeError),
        ({"object_types": ("",)}, ValueError),
        ({"qualifiers": "flow"}, TypeError),
        ({"qualifiers": (None,)}, TypeError),
    ],
)
def test_spec_rejects_mutable_or_invalid_selectors(kwargs, exception):
    with pytest.raises(exception):
        ObjectStatisticsSpec(**kwargs)


def test_canonical_input_permutations_context_and_normalized_spec_share_identity():
    log = example()
    reordered = replace(
        log, events=log.events[::-1], objects=log.objects[::-1], e2o=log.e2o[::-1]
    )
    a = object_statistics(
        log, ObjectStatisticsSpec(("parcel", "order", "order"), ("flow", "audit"))
    )
    b = object_statistics(
        ComputationContext(reordered),
        ObjectStatisticsSpec(("order", "parcel"), ("audit", "flow")),
    )
    assert a == b
    assert (
        object_statistics(
            log, ObjectStatisticsSpec(qualifiers=("flow",))
        ).computation_id
        != a.computation_id
    )
    with pytest.raises(FrozenInstanceError):
        a.value.object_count = 0


def test_large_duration_retains_integer_microseconds_beyond_float_precision():
    start = datetime(1000, 1, 1, tzinfo=timezone.utc)
    finish = datetime(9999, 12, 30, 23, 59, 59, 999999, tzinfo=timezone.utc)
    log = OCEL(
        (EventType("A"),),
        (ObjectType("O"),),
        (Event("first", "A", start), Event("last", "A", finish)),
        (Object("o", "O"),),
        (E2O("first", "o", ""), E2O("last", "o", "")),
        (),
    )
    (row,) = object_statistics(log).value.objects
    delta = finish - start
    assert row.duration_microseconds == delta // timedelta(microseconds=1)
    assert row.duration_microseconds % 1_000_000 == 999999


def test_exhaustive_two_event_two_object_matrices_against_independent_oracle():
    """All 16 binary incidence matrices, plus a second role on every present edge."""
    events = (Event("e1", "A", ORIGIN), Event("e2", "A", ORIGIN))
    objects = (Object("o1", "O"), Object("o2", "O"))
    cells = (("e1", "o1"), ("e1", "o2"), ("e2", "o1"), ("e2", "o2"))
    for mask in product((0, 1), repeat=4):
        selected = tuple(cell for cell, present in zip(cells, mask) if present)
        relations = tuple(
            E2O(e, o, role) for e, o in selected for role in ("flow", "audit")
        )
        log = OCEL(
            (EventType("A"),), (ObjectType("O"),), events, objects, relations, ()
        )
        value = object_statistics(log).value
        assert value.unique_participation_count == sum(mask)
        assert value.e2o_relation_count == 2 * sum(mask)
        degrees_objects = [mask[0] + mask[2], mask[1] + mask[3]]
        degrees_events = [mask[0] + mask[1], mask[2] + mask[3]]
        assert value.participating_object_count == sum(n > 0 for n in degrees_objects)
        assert value.participating_event_count == sum(n > 0 for n in degrees_events)
        if not selected:
            assert value.activity_object_types == ()
            continue
        (row,) = value.activity_object_types
        # With at most two positive samples, median > 1 iff their sum exceeds count.
        object_samples = [n for n in degrees_objects if n]
        event_samples = [n for n in degrees_events if n]
        assert row.divergence_median_gt_one == (
            sum(object_samples) > len(object_samples)
        )
        assert row.convergence_median_gt_one == (
            sum(event_samples) > len(event_samples)
        )
        assert dict(row.events_per_object_counts) == {
            obj.id: n for obj, n in zip(objects, degrees_objects) if n
        }
        assert dict(row.objects_per_event_counts) == {
            event.id: n for event, n in zip(events, degrees_events) if n
        }
