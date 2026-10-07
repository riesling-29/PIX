"""Hand-counted witness overlays, unknown populations and refused rebinding."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pix.case_centric.discovery import discover_footprints
from pix.case_centric.model_discovery import (
    ModelFootprintSpec,
    discover_model_footprints,
)
from pix.compute.conformance import align_traces
from pix.compute.replay import replay_traces
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeIssue, ComputeStatus, computation_identity
from pix.models import ModelArtifact
from pix.object_centric.conformance import ObjectReplaySpec, replay_object_log
from pix.object_centric.model_integration import EnhancedOCPNSpec, enhance_ocpn
from pix.object_centric.performance import (
    OCReplayPerformanceSpec,
    measure_replay_performance,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.results import result_from_json, result_json_bytes
from pix.viewer.visual_annotations import (
    footprint_comparison_panels,
    model_annotation_panels,
)
from pix.viewer.visual_contracts import GraphPanel, VisualizationDocument
from pix.viewer.visual_model_adapters import model_panels
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization


def log(*traces):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events, objects, relations = [], [], []
    for i, activities in enumerate(traces):
        objects.append(Object(f"o{i}", "order"))
        for j, activity in enumerate(activities):
            eid = f"e{i}.{j}"
            events.append(Event(eid, activity, origin + timedelta(seconds=j * 7)))
            relations.append(E2O(eid, f"o{i}", "flow"))
    return OCEL(
        event_types=tuple(EventType(a) for a in sorted({e.type for e in events})),
        object_types=(ObjectType("order"),),
        events=tuple(events),
        objects=tuple(objects),
        e2o=tuple(relations),
    )


def traces(*sequences):
    return reconstruct_traces(log(*sequences), TraceSpec("order"))


def net(*, duplicate=False, silent=False):
    labels = ("A", None if silent else "A" if duplicate else "B")
    return PetriNet(
        tuple(Place(p) for p in ("p", "q", "r")),
        tuple(Transition(t, a) for t, a in zip(("first", "second"), labels)),
        (Arc("p", "first"), Arc("first", "q"), Arc("q", "second"), Arc("second", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )


def ocnet(*, duplicate=True):
    base = net(duplicate=duplicate)
    return ObjectCentricPetriNet(
        tuple(TypedPlace(p.id, "order") for p in base.places),
        base.transitions,
        tuple(ObjectArc(a.source, a.target) for a in base.arcs),
        ObjectMarking((ObjectToken("p", "o0"),)),
        ObjectMarking((ObjectToken("r", "o0"),)),
        (("o0", "order"),),
    )


def graph(panels):
    return next(panel for panel in panels if type(panel) is GraphPanel)


def metric_values(panels):
    return {
        node.id: node.metrics[-1].value for node in graph(panels).nodes if node.metrics
    }


def details(node):
    return {field.name: field.value for field in node.details}


def checked_roundtrip(panels):
    document = VisualizationDocument("Witness visualization", panels)
    assert loads_visualization(dumps_visualization(document)) == document


@pytest.mark.parametrize(
    "metric, expected",
    [
        ("firing_count", {"first": 2, "second": 2}),
        ("inserted_tokens", {"first": 0, "second": 0}),
        ("consumed_tokens", {"first": 2, "second": 2}),
        ("produced_tokens", {"first": 2, "second": 2}),
    ],
)
def test_case_replay_hand_counted_and_preserves_model(metric, expected):
    model = net(duplicate=True)
    result = replay_traces(traces(("A", "A"), ("A", "A")), model)
    panels = model_annotation_panels(
        ModelArtifact(model, "provided"), result, metric=metric
    )
    assert metric_values(panels) == expected
    assert graph(panels).edges == graph(model_panels(model)).edges
    nodes = {node.id: node for node in graph(panels).nodes}
    assert nodes["first"].label == nodes["second"].label == "A"
    assert details(nodes["p"])["initial_count"] == 1
    assert details(nodes["r"])["final_count"] == 1
    checked_roundtrip(panels)


def test_inserted_tokens_are_attached_to_repaired_transition_only():
    model = net()
    panels = model_annotation_panels(
        model, replay_traces(traces(("B",)), model), metric="inserted_tokens"
    )
    assert metric_values(panels) == {"first": 0, "second": 1}


@pytest.mark.parametrize(
    "metric, expected",
    [
        ("firing_count", {"first": 1, "second": 1}),
        ("synchronous_count", {"first": 1, "second": 0}),
        ("model_move_count", {"first": 0, "second": 1}),
        ("silent_count", {"first": 0, "second": 0}),
    ],
)
def test_alignment_path_metric_is_not_activity_frequency(metric, expected):
    model = net()
    result = align_traces(traces(("A",)), model)
    panels = model_annotation_panels(
        model, result_from_json(result_json_bytes(result)), metric=metric
    )
    assert metric_values(panels) == expected
    checked_roundtrip(panels)


def test_silent_transition_retains_identity_and_firing_count():
    model = net(silent=True)
    panels = model_annotation_panels(
        model, align_traces(traces(("A",)), model), metric="silent_count"
    )
    assert metric_values(panels) == {"first": 0, "second": 1}
    assert (
        next(node for node in graph(panels).nodes if node.id == "second").kind
        == "silent"
    )


def test_limited_alignment_does_not_claim_whole_population_zero():
    model = net()
    result = align_traces(traces(("A", "B")), model, AlignmentSpec(max_states=1))
    panels = model_annotation_panels(model, result, metric="firing_count")
    assert metric_values(panels) == {"first": 0, "second": 0}
    assert all(
        details(node)["annotation_whole_population_known"] is False
        for node in graph(panels).nodes
        if node.metrics
    )


def test_unavailable_replay_binds_model_but_never_invents_zero_counts():
    model = net()
    result = replay_traces(traces(("A", "B")), model)
    unavailable = replace(
        result,
        status=ComputeStatus.UNAVAILABLE,
        value=None,
        issues=(
            ComputeIssue("upstream_unavailable", "No trace evidence is available"),
        ),
    )
    panels = model_annotation_panels(model, unavailable, metric="firing_count")
    assert metric_values(panels) == {"first": None, "second": None}
    checked_roundtrip(panels)


@pytest.mark.parametrize("kind", ["replay", "alignment", "object", "enhanced"])
def test_wrong_model_is_rejected(kind):
    if kind in ("replay", "alignment"):
        model = net()
        result = (replay_traces if kind == "replay" else align_traces)(
            traces(("A", "B")), model
        )
        wrong = net(duplicate=True)
    else:
        model = ocnet()
        spec = ObjectReplaySpec(("order",))
        result = (
            replay_object_log(log(("A", "A")), model, spec)
            if kind == "object"
            else enhance_ocpn(log(("A", "A")), model, EnhancedOCPNSpec(spec))
        )
        wrong = ocnet(duplicate=False)
    with pytest.raises(ValueError, match="model"):
        model_annotation_panels(wrong, result, metric="firing_count")


def test_source_or_request_tampering_is_refused():
    model = net()
    result = replay_traces(traces(("A", "B")), model)
    with pytest.raises(ValueError, match="identity"):
        model_annotation_panels(
            model, replace(result, source_digest="other-log"), metric="firing_count"
        )


def test_transition_label_cannot_substitute_for_transition_id():
    model = net()
    result = replay_traces(traces(("A", "B")), model)
    trace = result.value.traces[0]
    step = replace(trace.steps[1], transition_id="A")
    forged = replace(
        result,
        value=replace(
            result.value,
            traces=(replace(trace, steps=(trace.steps[0], step, *trace.steps[2:])),),
        ),
    )
    with pytest.raises(ValueError, match="transition"):
        model_annotation_panels(model, forged, metric="firing_count")


def test_model_move_cannot_consume_a_log_event():
    model = net()
    result = align_traces(traces(("A", "B")), model)
    path = result.value.alignments[0]
    move = replace(path.moves[0], kind="model", cost=1)
    forged = replace(
        result,
        value=replace(
            result.value,
            alignments=(replace(path, moves=(move, *path.moves[1:]), cost=1),),
            completed_cost_sum=1,
            total_cost=1,
            mean_completed_cost_ratio=(1, 1),
        ),
    )
    with pytest.raises(ValueError, match="event presence"):
        model_annotation_panels(model, forged, metric="model_move_count")


@pytest.mark.parametrize("metric", ["frequency", "performance", "fitness", ""])
def test_ambiguous_or_unsupported_metric_refused(metric):
    model = net()
    with pytest.raises(ValueError):
        model_annotation_panels(
            model, replay_traces(traces(("A", "B")), model), metric=metric
        )


def test_object_replay_uses_exact_joint_transition_witness():
    model = ocnet()
    result = replay_object_log(
        log(("A", "A")), model, ObjectReplaySpec(("order",), qualifiers=("flow",))
    )
    panels = model_annotation_panels(model, result, metric="firing_count")
    assert metric_values(panels) == {"first": 1, "second": 1}
    assert graph(panels).edges == graph(model_panels(model)).edges
    checked_roundtrip(panels)


def test_optional_zero_participation_is_a_valid_model_binding():
    model = ObjectCentricPetriNet(
        (TypedPlace("p", "order"),),
        (Transition("optional", "A"),),
        (ObjectArc("p", "optional", True, 0, 1),),
        ObjectMarking(),
        ObjectMarking(),
        (("o0", "order"),),
    )
    source = replace(log(("A",)), e2o=())
    result = replay_object_log(source, model, ObjectReplaySpec(("order",)))
    panels = model_annotation_panels(model, result, metric="firing_count")
    assert metric_values(panels) == {"optional": 1}
    checked_roundtrip(panels)


def test_same_label_transition_rebinding_cannot_hide_different_incidence():
    model = ocnet()
    result = replay_object_log(log(("A", "A")), model, ObjectReplaySpec(("order",)))
    step = result.value.steps[1]
    forged_step = replace(step, binding=replace(step.binding, transition_id="second"))
    forged = replace(
        result,
        value=replace(
            result.value,
            steps=(result.value.steps[0], forged_step, *result.value.steps[2:]),
        ),
    )
    with pytest.raises(ValueError, match="incidence"):
        model_annotation_panels(model, forged, metric="firing_count")


def test_enhanced_opera_uses_transition_identity_and_unknown_initial_time():
    model = ocnet()
    result = enhance_ocpn(
        log(("A", "A")),
        model,
        EnhancedOCPNSpec(
            ObjectReplaySpec(("order",)),
            OCReplayPerformanceSpec(metrics=("sojourn",), profile="ocpa_opera_1_3_4"),
        ),
    )
    with (
        patch(
            "pix.object_centric.conformance.replay_object_log",
            side_effect=AssertionError("viewer recomputed replay"),
        ),
        patch(
            "pix.object_centric.performance.measure_replay_performance",
            side_effect=AssertionError("viewer recomputed time"),
        ),
    ):
        panels = model_annotation_panels(
            model, result, metric="performance:sojourn:mean"
        )
    assert metric_values(panels) == {"first": None, "second": 7_000_000.0}
    nodes = {node.id: node for node in graph(panels).nodes}
    assert details(nodes["first"])["unknown_sample_count"] == 1
    assert details(nodes["second"])["mean_numerator"] == 7_000_000
    assert details(nodes["second"])["mean_denominator"] == 1
    checked_roundtrip(panels)


def test_standalone_timing_cannot_guess_duplicate_label_transition():
    model = ocnet()
    source = log(("A", "A"))
    replay = replay_object_log(source, model, ObjectReplaySpec(("order",)))
    result = measure_replay_performance(
        source, replay, OCReplayPerformanceSpec(metrics=("sojourn",))
    )
    panels = model_annotation_panels(model, result, metric="performance:sojourn:mean")
    assert graph(panels) == graph(model_panels(model))
    samples = next(panel for panel in panels if panel.id == "annotation_samples")
    assert all(row[1] is None for row in samples.rows)
    assert "unavailable" in samples.description
    checked_roundtrip(panels)


def test_enhanced_rebound_source_and_rehashed_envelope_still_refused():
    model = ocnet()
    result = enhance_ocpn(
        log(("A", "A")), model, EnhancedOCPNSpec(ObjectReplaySpec(("order",)))
    )
    other = "other-source"
    forged = replace(
        result,
        source_digest=other,
        computation_id=computation_identity(
            result.operator_id,
            result.operator_version,
            other,
            result.spec,
            result.parent_computation_ids,
        ),
    )
    with pytest.raises(ValueError, match="parent/source/selection"):
        model_annotation_panels(model, forged, metric="performance:sojourn:mean")


def test_enhanced_token_arrival_result_cannot_be_relabeled_as_opera():
    model = ocnet(duplicate=False)
    result = enhance_ocpn(
        log(("A", "B")),
        model,
        EnhancedOCPNSpec(
            ObjectReplaySpec(("order",)),
            OCReplayPerformanceSpec(activities=("B",)),
        ),
    )
    forged = replace(
        result,
        value=replace(
            result.value,
            performance=replace(result.value.performance, profile="ocpa_opera_1_3_4"),
        ),
    )
    with pytest.raises(ValueError, match="profile"):
        model_annotation_panels(model, forged, metric="performance:sojourn:mean")


def footprint(*sequences):
    return discover_footprints(traces(*sequences))


def cell(panel, a, b):
    return next(c for c in panel.cells if c.row == a and c.column == b)


def test_footprint_direction_and_symmetric_mismatch_are_distinct():
    left, right = footprint(("A", "B")), footprint(("B", "A"))
    panels = footprint_comparison_panels(left, right, symmetric=True)
    assert cell(panels[2], "A", "B").value == "directional_mismatch"
    parallel = footprint(("A", "B"), ("B", "A"))
    assert (
        cell(
            footprint_comparison_panels(left, parallel, symmetric=True)[2], "A", "B"
        ).value
        == "symmetry_mismatch"
    )
    checked_roundtrip(panels)


def test_directional_inclusion_does_not_flag_right_only_behavior():
    left, right = footprint(("A", "B")), footprint(("A", "B"), ("B", "A"))
    assert (
        cell(footprint_comparison_panels(left, right)[2], "A", "B").value == "supported"
    )
    assert (
        cell(footprint_comparison_panels(right, left)[2], "A", "B").value
        == "symmetry_mismatch"
    )


def test_union_alphabet_does_not_treat_missing_activity_as_no_relation():
    panels = footprint_comparison_panels(
        footprint(("A", "B")), footprint(("A", "C")), symmetric=True
    )
    assert panels[0].rows == panels[1].rows == ("A", "B", "C")
    assert cell(panels[1], "A", "B").value == "outside_alphabet"
    assert cell(panels[2], "A", "B").value == "unknown"
    assert cell(panels[0], "B", "B").value == "#"
    checked_roundtrip(panels)


def test_incomplete_model_footprint_unknown_is_not_none_relation():
    left = discover_model_footprints(net(), ModelFootprintSpec(max_states=1))
    right = footprint(("A", "B"))
    panels = footprint_comparison_panels(left, right, symmetric=True)
    assert cell(panels[0], "A", "B").value == "?"
    assert cell(panels[2], "A", "B").value == "unknown"
    checked_roundtrip(panels)


def test_partial_result_negative_footprints_stay_unknown():
    result = footprint(("A", "B"))
    partial = replace(
        result,
        status=ComputeStatus.PARTIAL,
        issues=(
            ComputeIssue(
                "coverage_limited", "Only part of the requested population is available"
            ),
        ),
    )
    panels = footprint_comparison_panels(partial, result, symmetric=True)
    assert cell(panels[0], "A", "B").value == "follows?"
    assert cell(panels[2], "A", "B").value == "unknown"


@pytest.mark.parametrize("bad", [1, None, "yes"])
def test_symmetric_requires_explicit_boolean(bad):
    model = footprint(("A",))
    with pytest.raises(TypeError):
        footprint_comparison_panels(model, model, symmetric=bad)
