"""Hand-checkable variant chevrons; supplied evidence, never rediscovery."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.executions import discover_executions
from pix.compute.variants import discover_variants
from pix.contracts.execution import (
    EventOrderEdge,
    EventOrderTie,
    ExecutionSpec,
    VariantSpec,
)
from pix.contracts.result import computation_identity
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer.visual_chevrons import (
    build_execution_chevrons,
    build_variant_visualization,
)
from pix.viewer.visual_contracts import (
    ChevronEvent,
    ChevronLane,
    ChevronPanel,
    VisualizationDocument,
)
from pix.viewer.visual_serialization import (
    dumps_visualization,
    loads_visualization,
    visual_to_dict,
)

BASE = datetime(2026, 9, 16, tzinfo=timezone.utc)


def log(rows, types):
    return OCEL(
        event_types=tuple(
            EventType(activity) for activity in sorted({row[1] for row in rows})
        ),
        object_types=tuple(ObjectType(kind) for kind in sorted(set(types.values()))),
        events=tuple(
            Event(eid, activity, BASE + timedelta(seconds=offset))
            for eid, activity, offset, _ in rows
        ),
        objects=tuple(Object(oid, kind) for oid, kind in sorted(types.items())),
        e2o=tuple(
            E2O(eid, oid, qualifier)
            for eid, _, _, relations in rows
            for oid, qualifier in relations
        ),
    )


def fork_join():
    # B on y waits for the longer x path A -> C -> D before shared E.
    return log(
        (
            ("a", "Start", 0, (("x", "flow"), ("y", "flow"))),
            ("b", "Short", 1, (("y", "flow"),)),
            ("c", "Work", 2, (("x", "flow"),)),
            ("d", "Work", 3, (("x", "flow"),)),
            ("e", "Join", 4, (("x", "flow"), ("y", "flow"), ("y", "audit"))),
        ),
        {"x": "Item", "y": "Item"},
    )


def results(source=None, spec=None):
    executions = discover_executions(
        source if source is not None else fork_join(),
        spec or ExecutionSpec("connected_components"),
    )
    return executions, discover_variants(executions, VariantSpec())


def identity(result, **changes):
    value = replace(result, **changes)
    return replace(
        value,
        computation_id=computation_identity(
            value.operator_id,
            value.operator_version,
            value.source_digest,
            value.spec,
            value.parent_computation_ids,
        ),
    )


def test_fork_join_stretches_short_branch_in_precedence_layers():
    execution = results()[0].value.executions[0]
    panel = build_execution_chevrons(execution)
    assert {event.id: (event.start, event.end) for event in panel.events} == {
        "a": (0, 0),
        "b": (1, 2),
        "c": (1, 1),
        "d": (2, 2),
        "e": (3, 3),
    }
    assert "not durations" in panel.description
    assert [lane.object_id for lane in panel.lanes] == ["x", "y"]
    assert {lane.object_type for lane in panel.lanes} == {"Item"}
    shared = next(event for event in panel.events if event.id == "e")
    assert shared.lane_ids == ("x", "y")
    assert len([event for event in panel.events if event.id == "e"]) == 1
    assert len([event for event in panel.events if event.label == "Work"]) == 2


def test_coordinates_ignore_elapsed_time_and_object_id_renaming():
    source = fork_join()
    changed = replace(
        source,
        events=tuple(
            replace(event, time=BASE + timedelta(days=index * 10))
            for index, event in enumerate(source.events)
        ),
    )
    first = build_execution_chevrons(results(source)[0].value.executions[0])
    second = build_execution_chevrons(results(changed)[0].value.executions[0])
    assert [(event.id, event.start, event.end) for event in first.events] == [
        (event.id, event.start, event.end) for event in second.events
    ]


def test_variant_document_preserves_frequency_qualifiers_and_sources():
    execution, variants = results()
    document = build_variant_visualization(execution, variants, title="Review")
    panel = next(panel for panel in document.panels if isinstance(panel, ChevronPanel))
    assert (panel.frequency, panel.population) == (1, 1)
    assert panel.variant_id == variants.value.variants[0].variant_id
    evidence = next(
        panel for panel in document.panels if panel.id == "variant-incidence-evidence"
    )
    assert len([row for row in evidence.rows if row[2:4] == ("e", "y")]) == 2
    assert {
        item.calculation_id for item in document.provenance if item.calculation_id
    } == {execution.computation_id, variants.computation_id}
    assert all(
        set(item.panel_ids) == {panel.id for panel in document.panels}
        for item in document.provenance
    )
    assert loads_visualization(dumps_visualization(document)) == document
    assert visual_to_dict(document)["panels"][1]["kind"] == "chevron"


def test_visualization_does_not_rediscover_or_canonicalize_variants(monkeypatch):
    import pix.compute.variants as variants_module

    execution, variants = results()

    def forbidden(*args, **kwargs):
        raise AssertionError("viewer must not calculate variants")

    monkeypatch.setattr(variants_module, "discover_variants", forbidden)
    monkeypatch.setattr(variants_module, "_canonical_form", forbidden)
    document = build_variant_visualization(execution, variants)
    assert any(isinstance(panel, ChevronPanel) for panel in document.panels)


def test_same_variant_groups_renamed_executions_with_correct_denominator():
    source = log(
        (
            ("a1", "A", 0, (("x", ""),)),
            ("b1", "B", 1, (("x", ""),)),
            ("a2", "A", 5, (("y", ""),)),
            ("b2", "B", 8, (("y", ""),)),
            ("a3", "C", 9, (("z", ""),)),
        ),
        {"x": "T", "y": "T", "z": "T"},
    )
    document = build_variant_visualization(*results(source))
    panels = [panel for panel in document.panels if isinstance(panel, ChevronPanel)]
    assert sorted((panel.frequency, panel.population) for panel in panels) == [
        (1, 3),
        (2, 3),
    ]
    frequency = next(
        panel for panel in document.panels if panel.id == "variant-frequencies"
    )
    assert sum(row[2] for row in frequency.rows) == 3


def test_boundary_objects_and_excluded_qualifiers_stay_as_evidence():
    source = log(
        (
            ("e1", "Receive", 0, (("O1", "flow"),)),
            ("e2", "Receive", 1, (("O2", "flow"),)),
            ("e3", "Pack", 2, (("O1", "flow"), ("I1", "flow"))),
            ("e4", "Pack", 3, (("O2", "flow"), ("I2", "flow"))),
            (
                "e5",
                "Ship",
                4,
                (("I1", "flow"), ("I2", "flow"), ("S", "flow"), ("I2", "audit")),
            ),
            ("e6", "Delivered", 5, (("S", "flow"),)),
        ),
        {"O1": "Order", "O2": "Order", "I1": "Item", "I2": "Item", "S": "Shipment"},
    )
    execution, variants = results(
        source,
        ExecutionSpec(
            "leading_object_nearest_type",
            leading_object_type="Order",
            qualifiers=("flow",),
        ),
    )
    document = build_variant_visualization(execution, variants)
    evidence = next(
        panel for panel in document.panels if panel.id == "variant-incidence-evidence"
    )
    assert any(row[6:] == ("boundary", "selected") for row in evidence.rows)
    assert any(row[5] == "audit" and row[7] == "excluded" for row in evidence.rows)
    for panel in (
        panel for panel in document.panels if isinstance(panel, ChevronPanel)
    ):
        representative = next(
            variant.representative_execution_id
            for variant in variants.value.variants
            if variant.variant_id == panel.variant_id
        )
        raw = next(
            item
            for item in execution.value.executions
            if item.execution_id == representative
        )
        assert {lane.object_id for lane in panel.lanes} == {
            obj.id for obj in raw.objects
        }
        assert not (
            {lane.object_id for lane in panel.lanes}
            & {obj.id for obj in raw.boundary_objects}
        )


def test_objectless_events_are_explicit_not_silently_dropped():
    execution, variants = results(log((("orphan", "Notice", 0, ()),), {}))
    with pytest.raises(ValueError, match="without an in-scope object"):
        build_execution_chevrons(execution.value.executions[0])
    document = build_variant_visualization(execution, variants)
    panel = next(panel for panel in document.panels if isinstance(panel, ChevronPanel))
    assert panel.events == panel.lanes == ()
    evidence = next(
        panel for panel in document.panels if panel.id == "variant-unlaned-events"
    )
    assert evidence.rows[0][2:4] == ("orphan", "Notice")


def test_empty_log_and_empty_leading_execution_are_supported():
    document = build_variant_visualization(*results(log((), {})))
    assert not any(isinstance(panel, ChevronPanel) for panel in document.panels)
    document = build_variant_visualization(
        *results(
            log((), {"empty": "Order"}),
            ExecutionSpec("leading_object_nearest_type", leading_object_type="Order"),
        )
    )
    panel = next(panel for panel in document.panels if isinstance(panel, ChevronPanel))
    assert panel.events == ()
    assert len(panel.lanes) == 1
    assert (panel.frequency, panel.population) == (1, 1)


def test_unresolved_ties_refused_and_explicit_ties_disclosed():
    source = log((("a", "A", 0, (("x", ""),)), ("b", "B", 0, (("x", ""),))), {"x": "T"})
    execution, variants = results(source)
    with pytest.raises(ValueError, match="complete order"):
        build_execution_chevrons(execution.value.executions[0])
    with pytest.raises(ValueError, match="complete"):
        build_variant_visualization(execution, variants)
    execution, variants = results(
        source, ExecutionSpec("connected_components", tie_policy="event_id")
    )
    document = build_variant_visualization(execution, variants)
    panel = next(panel for panel in document.panels if isinstance(panel, ChevronPanel))
    assert "tie breaking" in panel.description
    assert [(event.start, event.end) for event in panel.events] == [(0, 0), (1, 1)]


def test_incomplete_order_and_incorrect_tie_annotations_refused():
    execution = results()[0].value.executions[0]
    with pytest.raises(ValueError, match="complete object order"):
        build_execution_chevrons(
            replace(execution, order_edges=execution.order_edges[1:])
        )
    with pytest.raises(ValueError, match="tie_broken"):
        build_execution_chevrons(
            replace(
                execution,
                order_edges=(
                    replace(execution.order_edges[0], tie_broken=True),
                    *execution.order_edges[1:],
                ),
            )
        )
    with pytest.raises(ValueError, match="tie evidence"):
        build_execution_chevrons(
            replace(execution, order_ties=(EventOrderTie("x", ("a", "c"), BASE),))
        )


def test_cross_object_cycle_is_refused_even_when_each_object_is_a_path():
    source = log(
        (
            ("a", "A", 0, (("x", ""), ("z", ""))),
            ("b", "B", 0, (("x", ""), ("y", ""))),
            ("c", "C", 0, (("y", ""), ("z", ""))),
        ),
        {"x": "T", "y": "T", "z": "T"},
    )
    execution = results(
        source, ExecutionSpec("connected_components", tie_policy="event_id")
    )[0].value.executions[0]
    cyclic = replace(
        execution,
        order_edges=(
            EventOrderEdge("a", "b", "x", True),
            EventOrderEdge("b", "c", "y", True),
            EventOrderEdge("c", "a", "z", True),
        ),
    )
    with pytest.raises(ValueError, match="acyclic"):
        build_execution_chevrons(cyclic)


def test_source_parent_and_request_identity_must_match():
    execution, variants = results()
    with pytest.raises(ValueError, match="identity"):
        build_variant_visualization(
            replace(execution, computation_id="forged"), variants
        )
    with pytest.raises(ValueError, match="source identities"):
        build_variant_visualization(
            execution, identity(variants, source_digest="other")
        )
    with pytest.raises(ValueError, match="exactly.*parent"):
        build_variant_visualization(
            execution, identity(variants, parent_computation_ids=("other",))
        )
    with pytest.raises(ValueError, match="exactly.*parent"):
        build_variant_visualization(
            execution,
            identity(
                variants, parent_computation_ids=(execution.computation_id, "extra")
            ),
        )


def test_duplicate_variant_memberships_and_missing_representative_refused():
    source = log(
        (("a", "A", 0, (("x", ""),)), ("b", "B", 1, (("y", ""),))), {"x": "T", "y": "T"}
    )
    execution, variants = results(source)
    first, second = variants.value.variants
    repeated = replace(
        second,
        execution_ids=first.execution_ids,
        representative_execution_id=first.representative_execution_id,
    )
    with pytest.raises(ValueError, match="partition"):
        build_variant_visualization(
            execution,
            replace(
                variants, value=replace(variants.value, variants=(first, repeated))
            ),
        )
    missing = replace(
        second, execution_ids=("missing",), representative_execution_id="missing"
    )
    with pytest.raises(ValueError, match="partition"):
        build_variant_visualization(
            execution,
            replace(variants, value=replace(variants.value, variants=(first, missing))),
        )
    with pytest.raises(ValueError, match="variant IDs"):
        build_variant_visualization(
            execution,
            replace(
                variants,
                value=replace(
                    variants.value,
                    variants=(first, replace(second, variant_id=first.variant_id)),
                ),
            ),
        )


def test_forged_execution_membership_counters_refused():
    execution, variants = results()
    with pytest.raises(ValueError, match="membership counts"):
        build_variant_visualization(
            replace(
                execution, value=replace(execution.value, event_membership_count=999)
            ),
            variants,
        )
    with pytest.raises(ValueError, match="memberships disagree"):
        build_variant_visualization(
            replace(execution, value=replace(execution.value, event_memberships=())),
            variants,
        )


def test_selected_and_excluded_incidence_must_match_extraction_parameters():
    execution, variants = results(
        spec=ExecutionSpec("connected_components", qualifiers=("flow",))
    )
    original = execution.value.executions[0]

    def changed(record):
        return replace(execution, value=replace(execution.value, executions=(record,)))

    modified = replace(
        original,
        relations=(
            replace(original.relations[0], qualifier="not-selected"),
            *original.relations[1:],
        ),
    )
    with pytest.raises(ValueError, match="selected incidence contradicts"):
        build_variant_visualization(changed(modified), variants)
    modified = replace(
        original,
        # Drop one of the two x/y incidences from the shared event into excluded;
        # complete object path validation is still satisfied by changing its qualifier only.
        excluded_relations=(
            *original.excluded_relations,
            replace(original.relations[0], qualifier="flow"),
        ),
    )
    with pytest.raises(ValueError, match="disjoint"):
        build_variant_visualization(changed(modified), variants)
    # A new in-scope event/object pair in excluded also contradicts all-qualifier selection.
    all_execution, all_variants = results()
    all_original = all_execution.value.executions[0]
    extra = replace(all_original.relations[0], qualifier="extra-selected-qualifier")
    modified = replace(all_original, excluded_relations=(extra,))
    with pytest.raises(ValueError, match="excluded incidence contradicts"):
        build_variant_visualization(
            replace(
                all_execution,
                value=replace(all_execution.value, executions=(modified,)),
            ),
            all_variants,
        )


def test_leading_role_and_in_scope_types_must_match_request():
    execution, variants = results()
    original = execution.value.executions[0]
    modified = replace(original, leading_object_id=original.objects[0].id)
    with pytest.raises(ValueError, match="cannot declare a leading object"):
        build_variant_visualization(
            replace(execution, value=replace(execution.value, executions=(modified,))),
            variants,
        )
    execution, variants = results(
        log((), {"empty": "Order"}),
        ExecutionSpec(
            "leading_object_nearest_type",
            object_types=("Order",),
            leading_object_type="Order",
        ),
    )
    original = execution.value.executions[0]
    modified = replace(original, objects=(replace(original.objects[0], type="Other"),))
    with pytest.raises(ValueError, match="in-scope object type"):
        build_variant_visualization(
            replace(execution, value=replace(execution.value, executions=(modified,))),
            variants,
        )
    modified = replace(original, leading_object_id=None)
    with pytest.raises(ValueError, match="leading object must match"):
        build_variant_visualization(
            replace(execution, value=replace(execution.value, executions=(modified,))),
            variants,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"start": True},
        {"start": -1},
        {"end": 0.0},
        {"start": 2, "end": 1},
        {"lane_ids": ()},
        {"lane_ids": ("x", "x")},
        {"lane_ids": ("",)},
    ],
)
def test_chevron_event_strict_contract(changes):
    with pytest.raises((ValueError, TypeError)):
        ChevronEvent(
            **(
                {"id": "e", "label": "A", "start": 0, "end": 0, "lane_ids": ("x",)}
                | changes
            )
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"frequency": 1},
        {"population": 1},
        {"frequency": True, "population": 1},
        {"frequency": 0, "population": 0},
        {"frequency": 2, "population": 1},
        {"frequency": -1, "population": 1},
        {"lanes": (ChevronLane("x", "X", "T", "x"), ChevronLane("y", "Y", "T", "x"))},
        {"events": (ChevronEvent("e", "A", 0, 0, ("missing",)),)},
    ],
)
def test_chevron_panel_strict_contract(changes):
    with pytest.raises((ValueError, TypeError)):
        ChevronPanel(
            **(
                {"id": "p", "title": "P", "lanes": (ChevronLane("x", "X", "T", "x"),)}
                | changes
            )
        )


def test_chevron_hostile_text_roundtrip_and_unknown_json_fields():
    panel = ChevronPanel(
        "p",
        "<script>",
        (ChevronLane("x", "한글 <&>", "T", "x"),),
        (ChevronEvent("e", "</script>", 0, 2, ("x",)),),
    )
    document = VisualizationDocument("Review", (panel,))
    assert loads_visualization(dumps_visualization(document)) == document
    payload = visual_to_dict(document)
    payload["panels"][0]["events"][0]["duration"] = 10
    import json

    with pytest.raises(ValueError, match="unknown"):
        loads_visualization(json.dumps(payload))
