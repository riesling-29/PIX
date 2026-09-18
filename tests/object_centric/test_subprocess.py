"""Independent typed reachability, boundary, and transformation oracles."""

from collections import Counter
from dataclasses import FrozenInstanceError, asdict, replace
from itertools import product

import pytest

from pix.compute.model_semantics import model_digest
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.models import ObjectHidingSpec, ObjectReductionSpec
from pix.object_centric.subprocess import (
    ObjectSubprocessPipelineSpec,
    ObjectTypedSubprocessSpec,
    SubprocessCutArc,
    SubprocessTransitionContext,
    local_ocpn_subprocess,
    transform_ocpn_subprocess,
    validate_subprocess_result,
)


def marking(*tokens):
    return ObjectMarking(tuple(ObjectToken(*token) for token in tokens))


def shared_net():
    return ObjectCentricPetriNet(
        tuple(TypedPlace(pid, "item") for pid in ("p0", "p1", "p2", "p3", "isolated"))
        + (TypedPlace("o0", "order"), TypedPlace("o1", "order")),
        (
            Transition("a", "Inspect"),
            Transition("s", "Ship"),
            Transition("b", "Inspect"),
        ),
        (
            ObjectArc("p0", "a"),
            ObjectArc("a", "p1"),
            ObjectArc("p1", "s", True, 1, None),
            ObjectArc("s", "p2", True, 1, None),
            ObjectArc("p2", "b"),
            ObjectArc("b", "p3"),
            ObjectArc("o0", "s"),
            ObjectArc("s", "o1"),
        ),
        marking(("p0", "i1"), ("p0", "i1"), ("p1", "i2"), ("o0", "o1")),
        marking(("p3", "i1"), ("p2", "i2"), ("o1", "o1")),
        (("i1", "item"), ("i2", "item"), ("unmarked", "item"), ("o1", "order")),
    )


def spec(source="a", target="b", kind="item"):
    return ObjectTypedSubprocessSpec(kind, source, target)


def nodes(net):
    return {p.id for p in net.places} | {t.id for t in net.transitions}


def test_exact_between_subnet_and_shared_sync_cut():
    source = shared_net()
    before, digest = asdict(source), model_digest(source)
    result = local_ocpn_subprocess(source, spec())
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert value.reachable
    assert nodes(value.model) == {"a", "p1", "s", "p2", "b"}
    assert value.shared_transition_ids == ("s",)
    assert value.transition_context == (
        SubprocessTransitionContext("a", ("item",)),
        SubprocessTransitionContext("b", ("item",)),
        SubprocessTransitionContext("s", ("item", "order")),
    )
    assert {(row.arc.source, row.arc.target) for row in value.incoming_cut_arcs} == {
        ("p0", "a"),
        ("o0", "s"),
    }
    assert {(row.arc.source, row.arc.target) for row in value.outgoing_cut_arcs} == {
        ("b", "p3"),
        ("s", "o1"),
    }
    assert value.model.arcs == tuple(
        a
        for a in source.arcs
        if a.source in nodes(value.model) and a.target in nodes(value.model)
    )
    assert {t.id for t in value.model.transitions if t.activity == "Inspect"} == {
        "a",
        "b",
    }
    assert value.source_model_digest == result.source_digest == digest
    assert asdict(source) == before
    assert model_digest(source) == digest
    assert "not_execution_soundness_or_language_evidence" in value.meaning


def test_marking_partition_preserves_multiplicity_without_inventing_boundary_tokens():
    net = shared_net()
    value = local_ocpn_subprocess(net, spec()).value
    assert value.model.initial_marking == marking(("p1", "i2"))
    assert value.model.final_marking == marking(("p2", "i2"))
    for original, inside, outside in (
        (
            net.initial_marking,
            value.model.initial_marking,
            value.omitted_initial_marking,
        ),
        (net.final_marking, value.model.final_marking, value.omitted_final_marking),
    ):
        assert Counter(inside.tokens) + Counter(outside.tokens) == Counter(
            original.tokens
        )
    assert Counter(value.omitted_initial_marking.tokens)[ObjectToken("p0", "i1")] == 2
    assert value.model.objects == (("i1", "item"), ("i2", "item"), ("unmarked", "item"))


def test_cross_type_only_path_does_not_establish_typed_reachability():
    net = ObjectCentricPetriNet(
        (
            TypedPlace("i0", "item"),
            TypedPlace("i1", "item"),
            TypedPlace("middle", "order"),
        ),
        (Transition("a", "A"), Transition("b", "B")),
        (
            ObjectArc("i0", "a"),
            ObjectArc("a", "middle"),
            ObjectArc("middle", "b"),
            ObjectArc("b", "i1"),
        ),
        ObjectMarking(),
        ObjectMarking(),
        (),
    )
    value = local_ocpn_subprocess(net, spec()).value
    assert not value.reachable
    assert nodes(value.model) == set()
    assert not value.incoming_cut_arcs and not value.outgoing_cut_arcs
    assert local_ocpn_subprocess(net, spec("a", "b", "order")).value.reachable


def cyclic_net():
    source = shared_net()
    return replace(
        source,
        places=source.places + (TypedPlace("cycle", "item"),),
        transitions=source.transitions + (Transition("loop"),),
        arcs=source.arcs
        + (
            ObjectArc("s", "cycle", True, 1, None),
            ObjectArc("cycle", "loop"),
            ObjectArc("loop", "p1"),
        ),
    )


def test_cycles_are_walk_members_not_only_simple_path_members():
    value = local_ocpn_subprocess(cyclic_net(), spec()).value
    assert nodes(value.model) == {"a", "p1", "s", "p2", "b", "cycle", "loop"}


def test_equal_source_target_selects_scc_with_zero_length_walk():
    value = local_ocpn_subprocess(cyclic_net(), spec("s", "s")).value
    assert value.reachable
    assert nodes(value.model) == {"s", "cycle", "loop", "p1"}
    isolated = local_ocpn_subprocess(shared_net(), spec("isolated", "isolated")).value
    assert isolated.reachable
    assert nodes(isolated.model) == {"isolated"}
    assert not isolated.model.arcs
    transition = local_ocpn_subprocess(shared_net(), spec("s", "s")).value
    assert transition.reachable
    assert nodes(transition.model) == {"s"}
    assert len(transition.incoming_cut_arcs) == len(transition.outgoing_cut_arcs) == 2


def test_unreachable_valid_boundaries_report_empty_and_all_markings_omitted():
    source = shared_net()
    result = local_ocpn_subprocess(source, spec("b", "a"))
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert not value.reachable
    assert value.model.places == value.model.transitions == value.model.arcs == ()
    assert value.transition_context == ()
    assert value.omitted_initial_marking == source.initial_marking
    assert value.omitted_final_marking == source.final_marking
    assert value.model.objects == (("i1", "item"), ("i2", "item"), ("unmarked", "item"))


def test_cut_arc_preserves_type_cardinality_and_original_transition_label():
    value = local_ocpn_subprocess(shared_net(), spec("s", "s")).value
    item_in = next(
        row for row in value.incoming_cut_arcs if row.place.object_type == "item"
    )
    assert item_in.arc == ObjectArc("p1", "s", True, 1, None)
    assert item_in.transition == Transition("s", "Ship")
    assert item_in.place == TypedPlace("p1", "item")


def test_floyd_warshall_oracle_all_typed_node_pairs():
    """Independent transitive closure, including every pair and zero-length walk."""
    net = cyclic_net()
    typed_places = {p.id for p in net.places if p.object_type == "item"}
    incidence = [
        (a.source, a.target)
        for a in net.arcs
        if a.source in typed_places or a.target in typed_places
    ]
    vertices = sorted(typed_places | {x for pair in incidence for x in pair})
    reach = {
        (u, v): u == v or (u, v) in incidence for u, v in product(vertices, repeat=2)
    }
    for pivot in vertices:
        for u, v in product(vertices, repeat=2):
            reach[u, v] |= reach[u, pivot] and reach[pivot, v]
    for u, v in product(vertices, repeat=2):
        value = local_ocpn_subprocess(net, spec(u, v)).value
        expected = {x for x in vertices if reach[u, x] and reach[x, v]}
        assert nodes(value.model) == expected
        assert value.reachable is reach[u, v]


def test_row_order_determinism_and_immutable_payload():
    source = shared_net()
    reordered = replace(
        source,
        places=tuple(reversed(source.places)),
        transitions=tuple(reversed(source.transitions)),
        arcs=tuple(reversed(source.arcs)),
        objects=tuple(reversed(source.objects)),
        initial_marking=ObjectMarking(tuple(reversed(source.initial_marking.tokens))),
    )
    first = local_ocpn_subprocess(source, spec())
    assert first == local_ocpn_subprocess(reordered, spec())
    with pytest.raises(FrozenInstanceError):
        first.value.reachable = False
    with pytest.raises(FrozenInstanceError):
        first.value.incoming_cut_arcs[0].arc = ObjectArc("x", "y")


@pytest.mark.parametrize(
    "selection",
    [
        spec("missing", "b"),
        spec("a", "missing"),
        spec("o0", "b"),
        spec("a", "b", "unknown"),
        spec("isolated", "s", "order"),
    ],
)
def test_invalid_boundary_or_type_rejected(selection):
    with pytest.raises(ValueError):
        local_ocpn_subprocess(shared_net(), selection)


@pytest.mark.parametrize("value", [None, 1, [], True])
def test_invalid_call_types_rejected(value):
    with pytest.raises(TypeError):
        local_ocpn_subprocess(value, spec())
    with pytest.raises(TypeError):
        local_ocpn_subprocess(shared_net(), value)
    with pytest.raises(TypeError):
        transform_ocpn_subprocess(shared_net(), value)


def test_spec_and_metadata_validation():
    with pytest.raises(ValueError):
        ObjectTypedSubprocessSpec("", "a", "b")
    with pytest.raises((TypeError, ValueError)):
        ObjectTypedSubprocessSpec("item", [], "b")
    with pytest.raises(TypeError):
        SubprocessTransitionContext("a", ["item"])
    with pytest.raises(ValueError):
        SubprocessTransitionContext("a", ("item", "item"))
    with pytest.raises(ValueError):
        SubprocessTransitionContext("a", ())
    with pytest.raises(ValueError):
        SubprocessCutArc(ObjectArc("p", "b"), TypedPlace("p", "item"), Transition("a"))
    with pytest.raises(TypeError):
        ObjectSubprocessPipelineSpec(spec(), hiding=[])
    with pytest.raises(TypeError):
        ObjectSubprocessPipelineSpec(spec(), reduction=[])
    with pytest.raises(TypeError):
        ObjectSubprocessPipelineSpec(None)


@pytest.mark.parametrize(
    "changes",
    [
        {"reachable": 1},
        {"reachable": False},
        {"meaning": "sound_subprocess"},
        {"transition_context": ()},
        {"incoming_cut_arcs": []},
        {"omitted_initial_marking": marking(("p1", "i2"))},
    ],
)
def test_profile_rejects_corrupt_evidence(changes):
    value = local_ocpn_subprocess(shared_net(), spec()).value
    with pytest.raises((TypeError, ValueError)):
        replace(value, **changes)


def test_profile_rejects_duplicate_or_reversed_cuts_and_false_memberships():
    value = local_ocpn_subprocess(shared_net(), spec()).value
    with pytest.raises(ValueError, match="duplicate"):
        replace(value, incoming_cut_arcs=value.incoming_cut_arcs * 2)
    with pytest.raises(ValueError, match="direction"):
        replace(value, incoming_cut_arcs=value.outgoing_cut_arcs)
    contexts = tuple(
        SubprocessTransitionContext(row.transition_id, ("item",))
        for row in value.transition_context
    )
    with pytest.raises(ValueError, match="cut type"):
        replace(value, transition_context=contexts)


def test_pipeline_type_projection_then_exact_boundary_restriction():
    source = shared_net()
    before = asdict(source)
    result = transform_ocpn_subprocess(source, ObjectSubprocessPipelineSpec(spec()))
    value = result.value
    assert value.profile == local_ocpn_subprocess(source, spec()).value
    assert value.model == value.profile.model
    assert value.boundary_removed_place_ids == ("isolated", "p0", "p3")
    assert value.boundary_removed_transition_ids == ()
    assert value.projection.removed_place_ids == ("o0", "o1")
    assert value.hiding is value.reduction is None
    assert len(result.parent_computation_ids) == 2
    assert any("remove_synchronization" in loss for loss in value.semantic_losses)
    assert asdict(source) == before


def test_pipeline_preserves_place_only_zero_length_and_marking_multiplicity():
    source = ObjectCentricPetriNet(
        (TypedPlace("p", "item"),),
        (),
        (),
        marking(("p", "x"), ("p", "x")),
        marking(("p", "x")),
        (("x", "item"),),
    )
    value = transform_ocpn_subprocess(
        source, ObjectSubprocessPipelineSpec(spec("p", "p"))
    ).value
    assert value.model == source
    assert not value.boundary_removed_place_ids
    assert not value.boundary_removed_transition_ids


def series_net():
    return ObjectCentricPetriNet(
        tuple(TypedPlace(p, "item") for p in ("start", "p", "q", "end")),
        (Transition("a", "A"), Transition("hide", "Hidden"), Transition("b", "B")),
        tuple(
            ObjectArc(a, b)
            for a, b in (
                ("start", "a"),
                ("a", "p"),
                ("p", "hide"),
                ("hide", "q"),
                ("q", "b"),
                ("b", "end"),
            )
        ),
        marking(("start", "x")),
        marking(("end", "x")),
        (("x", "item"),),
    )


def test_pipeline_hides_then_reduces_keeping_original_identity_evidence():
    source = series_net()
    result = transform_ocpn_subprocess(
        source,
        ObjectSubprocessPipelineSpec(
            spec("start", "end"),
            ObjectHidingSpec(("hide",)),
            ObjectReductionSpec(rules=("series_places",)),
        ),
    )
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert len(result.parent_computation_ids) == 4
    assert value.hiding.hidden_transition_ids == ("hide",)
    assert value.reduction.steps[0].removed_transition_ids == ("hide",)
    assert "hide" not in nodes(value.model)
    assert "hide" in nodes(value.profile.model)
    assert value.model == value.reduction.model
    assert "selected_visible_activity_labels_are_hidden" in value.semantic_losses
    assert "silent_divergence" in value.semantic_losses
    assert next(t for t in source.transitions if t.id == "hide").activity == "Hidden"


def test_partial_reduction_propagates_status_and_issues():
    source = ObjectCentricPetriNet(
        tuple(TypedPlace(p, "item") for p in ("p", "q", "r")),
        (Transition("t1"), Transition("t2")),
        tuple(
            ObjectArc(a, b)
            for a, b in (("p", "t1"), ("t1", "q"), ("q", "t2"), ("t2", "r"))
        ),
        marking(("p", "x")),
        marking(("r", "x")),
        (("x", "item"),),
    )
    result = transform_ocpn_subprocess(
        source,
        ObjectSubprocessPipelineSpec(
            spec("p", "r"),
            reduction=ObjectReductionSpec(rules=("series_places",), max_steps=1),
        ),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.issues[0].code == "reduction_step_limit"
    assert len(result.value.reduction.steps) == 1
    assert not result.value.reduction.fixed_point_reached
    validate_subprocess_result(result)
    with pytest.raises(ValueError, match="status"):
        validate_subprocess_result(
            replace(result, status=ComputeStatus.COMPUTED, issues=())
        )


@pytest.mark.parametrize(
    "options",
    [
        {"hiding": ObjectHidingSpec(("a",))},
        {"reduction": ObjectReductionSpec(sacred_node_ids=("a",))},
    ],
)
def test_pipeline_rejects_options_outside_selected_model(options):
    with pytest.raises(ValueError):
        transform_ocpn_subprocess(
            shared_net(), ObjectSubprocessPipelineSpec(spec("s", "s"), **options)
        )


def test_pipeline_unreachable_restriction_and_identity():
    net = shared_net()
    request = ObjectSubprocessPipelineSpec(spec("b", "a"))
    result = transform_ocpn_subprocess(net, request)
    assert result.status is ComputeStatus.COMPUTED
    assert not nodes(result.value.model)
    assert result.value.boundary_removed_transition_ids == ("a", "b", "s")
    assert result == transform_ocpn_subprocess(net, request)
    assert (
        result.computation_id
        != transform_ocpn_subprocess(
            net, ObjectSubprocessPipelineSpec(spec())
        ).computation_id
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"boundary_removed_place_ids": ()},
        {"boundary_removed_transition_ids": ("a",)},
        {"semantic_losses": ()},
        {"model": shared_net()},
    ],
)
def test_pipeline_rejects_inconsistent_ledger(changes):
    value = transform_ocpn_subprocess(
        shared_net(), ObjectSubprocessPipelineSpec(spec())
    ).value
    with pytest.raises(ValueError):
        replace(value, **changes)


def test_pipeline_rejects_forged_reduction_with_unrelated_model():
    request = ObjectSubprocessPipelineSpec(
        spec("start", "end"), reduction=ObjectReductionSpec()
    )
    value = transform_ocpn_subprocess(series_net(), request).value
    unrelated = shared_net()
    forged = replace(
        value.reduction, model=unrelated, steps=(), original_to_reduced_places=()
    )
    with pytest.raises(ValueError, match="reduction ledger"):
        replace(value, reduction=forged, model=unrelated)
    with pytest.raises(ValueError, match="reduction stage"):
        replace(value, reduction=None)


def test_hiding_already_silent_transition_does_not_claim_a_visible_label_loss():
    source = series_net()
    source = replace(
        source,
        transitions=tuple(
            Transition(t.id) if t.id == "hide" else t for t in source.transitions
        ),
    )
    value = transform_ocpn_subprocess(
        source,
        ObjectSubprocessPipelineSpec(
            spec("start", "end"), hiding=ObjectHidingSpec(("hide",))
        ),
    ).value
    assert "selected_visible_activity_labels_are_hidden" not in value.semantic_losses


def test_subprocess_results_roundtrip_through_public_result_contract():
    from pix import results

    source = shared_net()
    computed = (
        local_ocpn_subprocess(source, spec()),
        transform_ocpn_subprocess(source, ObjectSubprocessPipelineSpec(spec())),
        transform_ocpn_subprocess(
            series_net(),
            ObjectSubprocessPipelineSpec(
                spec("start", "end"),
                ObjectHidingSpec(("hide",)),
                ObjectReductionSpec(rules=("series_places",)),
            ),
        ),
    )
    for result in computed:
        validate_subprocess_result(result)
        assert results.result_from_json(results.result_json_bytes(result)) == result


def test_profile_rejects_ghost_type_and_cut_endpoint_role_reversal():
    value = local_ocpn_subprocess(shared_net(), spec()).value
    contexts = tuple(
        replace(row, original_object_types=row.original_object_types + ("ghost",))
        for row in value.transition_context
    )
    with pytest.raises(ValueError, match="match exactly"):
        replace(value, transition_context=contexts)
    fake = SubprocessCutArc(
        ObjectArc("bogus", "a"), TypedPlace("a", "item"), Transition("bogus")
    )
    with pytest.raises(ValueError, match="disjoint"):
        replace(value, incoming_cut_arcs=value.incoming_cut_arcs + (fake,))


def test_profile_rejects_conflicting_cut_cardinality_and_endpoint_records():
    value = local_ocpn_subprocess(shared_net(), spec("s", "s")).value
    wrong_policy = tuple(
        replace(row, arc=ObjectArc(row.arc.source, row.arc.target, True, 0, 3))
        if row.place.id == "p1"
        else row
        for row in value.incoming_cut_arcs
    )
    with pytest.raises(ValueError, match="cardinality"):
        replace(value, incoming_cut_arcs=wrong_policy)
    wrong_transition = tuple(
        replace(row, transition=Transition("s", "Wrong"))
        if row.place.id == "p1"
        else row
        for row in value.incoming_cut_arcs
    )
    with pytest.raises(ValueError, match="transition"):
        replace(value, incoming_cut_arcs=wrong_transition)


def test_omitted_objects_record_even_unmarked_foreign_objects():
    source = shared_net()
    source = replace(source, objects=source.objects + (("unmarked-order", "order"),))
    value = local_ocpn_subprocess(source, spec()).value
    assert value.omitted_objects == (("o1", "order"), ("unmarked-order", "order"))
    assert tuple(sorted(value.model.objects + value.omitted_objects)) == source.objects
    with pytest.raises(ValueError, match="unique"):
        replace(value, omitted_objects=value.omitted_objects + (("i1", "order"),))
    with pytest.raises(ValueError, match="declared"):
        replace(value, omitted_initial_marking=marking(("p0", "unknown")))
    with pytest.raises(ValueError, match="transition as a place"):
        replace(value, omitted_initial_marking=marking(("a", "i1")))


@pytest.mark.parametrize("pipeline", [False, True])
def test_envelope_rejects_spec_source_and_parent_tampering(pipeline):
    source = shared_net()
    result = (
        transform_ocpn_subprocess(source, ObjectSubprocessPipelineSpec(spec()))
        if pipeline
        else local_ocpn_subprocess(source, spec())
    )
    different_spec = (
        ObjectSubprocessPipelineSpec(spec("s", "s")) if pipeline else spec("s", "s")
    )
    for changes in (
        {"spec": different_spec},
        {"source_digest": "wrong"},
        {"parent_computation_ids": ("forged",)},
    ):
        with pytest.raises(ValueError):
            validate_subprocess_result(replace(result, **changes))
