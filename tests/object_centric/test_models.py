"""Hand-worked joins/splits and independent finite firing oracles for OC models."""

from collections import Counter
from dataclasses import FrozenInstanceError, replace
from itertools import combinations, product
from unittest.mock import patch

import pytest

from pix.compute.model_semantics import fire_binding
from pix.contracts.models import (
    Binding,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.models import (
    RESULT_SCHEMAS,
    CausalChannel,
    CausalFiring,
    CausalMarker,
    CausalMarkerGroup,
    ObjectCentricCausalNet,
    ObjectConversionSpec,
    ObjectHidingSpec,
    ObjectInvariantSpec,
    ObjectProjectionSpec,
    ObjectReductionSpec,
    ObjectSoundnessSpec,
    ObjectSubnetSpec,
    analyze_ocpn_soundness,
    causal_firing_objects,
    causal_net_digest,
    causal_net_to_ocpn,
    enumerate_enabled_causal_bindings,
    fire_causal_binding,
    hide_ocpn,
    is_causal_binding_enabled,
    object_place_invariants,
    object_subnet,
    ocpn_to_causal_net,
    project_ocpn,
    reduce_ocpn,
)


def marking(*pairs):
    return ObjectMarking(tuple(ObjectToken(*pair) for pair in pairs))


def shipping():
    return ObjectCentricPetriNet(
        (
            TypedPlace("or", "order"),
            TypedPlace("od", "order"),
            TypedPlace("ir", "item"),
            TypedPlace("id", "item"),
        ),
        (Transition("ship", "Ship"),),
        (
            ObjectArc("or", "ship"),
            ObjectArc("ship", "od"),
            ObjectArc("ir", "ship", True, 1, 2),
            ObjectArc("ship", "id", True, 1, 2),
        ),
        marking(("or", "o"), ("ir", "i1"), ("ir", "i2")),
        marking(("od", "o"), ("id", "i1"), ("id", "i2")),
        (("o", "order"), ("i1", "item"), ("i2", "item")),
    )


def series(*, variable=False):
    return ObjectCentricPetriNet(
        tuple(TypedPlace(p, "item") for p in ("start", "p", "q", "end")),
        (Transition("a", "A"), Transition("tau"), Transition("b", "B")),
        (
            ObjectArc("start", "a"),
            ObjectArc("a", "p"),
            ObjectArc("p", "tau", variable, 1, 2 if variable else 1),
            ObjectArc("tau", "q", variable, 1, 2 if variable else 1),
            ObjectArc("q", "b"),
            ObjectArc("b", "end"),
        ),
        marking(("start", "x")),
        marking(("end", "x")),
        (("x", "item"),),
    )


def brute_language(net, *, max_visible=4, max_steps=8):
    """Enumerate concrete sets and token arithmetic without PIX binding search.

    Oracle intentionally explores full finite powersets, suitable only for the
    small fixtures here. It does not use the production enabled/fire routines.
    """
    types = {p.id: p.object_type for p in net.places}
    labels = {t.id: t.activity for t in net.transitions}
    candidates = []
    for transition in net.transitions:
        rows = [a for a in net.arcs if transition.id in (a.source, a.target)]
        policies = {
            types[a.source if a.target == transition.id else a.target]: (
                a.min_objects,
                a.max_objects,
            )
            for a in rows
        }
        options = []
        for kind, (low, high) in sorted(policies.items()):
            ids = tuple(obj for obj, ot in net.objects if ot == kind)
            options.append(
                tuple(
                    (kind, subset)
                    for size in range(
                        low, min(high if high is not None else len(ids), len(ids)) + 1
                    )
                    for subset in combinations(ids, size)
                )
            )
        for selection in product(*options):
            selected = dict(selection)
            consumed = Counter(
                ObjectToken(a.source, obj)
                for a in rows
                if a.target == transition.id
                for obj in selected[types[a.source]]
            )
            produced = Counter(
                ObjectToken(a.target, obj)
                for a in rows
                if a.source == transition.id
                for obj in selected[types[a.target]]
            )
            participants = tuple(
                sorted((obj, kind) for kind, ids in selection for obj in ids)
            )
            candidates.append((transition.id, consumed, produced, participants))
    accepted = set()
    pending = [(net.initial_marking, (), 0)]
    visited = set()
    while pending:
        state, word, depth = pending.pop()
        if (state, word, depth) in visited:
            continue
        visited.add((state, word, depth))
        if state == net.final_marking:
            accepted.add(word)
        if depth >= max_steps:
            continue
        counts = Counter(state.tokens)
        for tid, consumed, produced, participants in candidates:
            if consumed - counts:
                continue
            if labels[tid] is not None and len(word) >= max_visible:
                continue
            next_counts = counts.copy()
            next_counts.subtract(consumed)
            next_counts.update(produced)
            next_word = (
                word if labels[tid] is None else word + ((labels[tid], participants),)
            )
            pending.append(
                (ObjectMarking(tuple(next_counts.elements())), next_word, depth + 1)
            )
    return accepted


def causal_shipping():
    return ocpn_to_causal_net(shipping()).value.causal_net


def split_causal(*, disjoint=True, equality=False):
    """Two objects arrive together then choose two distinct outgoing channels."""
    return ObjectCentricCausalNet(
        (
            Transition("split", "Split"),
            Transition("left", "Left"),
            Transition("right", "Right"),
        ),
        (
            CausalChannel("entry", "item", None, "split"),
            CausalChannel("l", "item", "split", "left"),
            CausalChannel("r", "item", "split", "right"),
            CausalChannel("lend", "item", "left", None),
            CausalChannel("rend", "item", "right", None),
        ),
        (
            CausalMarkerGroup("si", "split", (CausalMarker("entry", 2, 2),)),
            CausalMarkerGroup("li", "left", (CausalMarker("l"),)),
            CausalMarkerGroup("ri", "right", (CausalMarker("r"),)),
        ),
        (
            CausalMarkerGroup(
                "so",
                "split",
                (CausalMarker("l"), CausalMarker("r")),
                (("l", "r"),) if equality else (),
                (("l", "r"),) if disjoint else (),
            ),
            CausalMarkerGroup("lo", "left", (CausalMarker("lend"),)),
            CausalMarkerGroup("ro", "right", (CausalMarker("rend"),)),
        ),
        marking(("entry", "x"), ("entry", "y")),
        marking(("lend", "x"), ("rend", "y")),
        (("x", "item"), ("y", "item")),
    )


def test_object_type_projection_retains_marking_multiplicity_and_documents_cut():
    net = shipping()
    projected = project_ocpn(net, ObjectProjectionSpec(object_types=("item",))).value
    assert {p.id for p in projected.model.places} == {"ir", "id"}
    assert projected.model.objects == (("i1", "item"), ("i2", "item"))
    assert projected.model.initial_marking == marking(("ir", "i1"), ("ir", "i2"))
    assert projected.removed_place_ids == ("od", "or")
    assert projected.behavioral_guarantee == "structural_projection_only"
    assert "additional bindings" in projected.boundary_note
    assert project_ocpn(net).value.model == net


def test_subprocess_projection_keeps_incident_boundary_places_without_invented_tokens():
    net = series()
    projected = project_ocpn(
        net, ObjectProjectionSpec(transition_ids=("tau",))
    ).value.model
    assert {p.id for p in projected.places} == {"p", "q"}
    assert projected.initial_marking == projected.final_marking == ObjectMarking()
    assert projected.objects == net.objects
    empty = project_ocpn(net, ObjectProjectionSpec(object_types=())).value.model
    assert not empty.places and not empty.transitions and not empty.objects
    with pytest.raises(ValueError):
        project_ocpn(net, ObjectProjectionSpec(object_types=("missing",)))


def test_hiding_keeps_every_concrete_token_effect():
    net = shipping()
    hidden = hide_ocpn(net, ObjectHidingSpec(("ship",))).value
    binding = Binding("ship", (("order", ("o",)), ("item", ("i1", "i2"))))
    assert fire_binding(net, net.initial_marking, binding) == fire_binding(
        hidden.model, hidden.model.initial_marking, binding
    )
    assert hidden.model.transitions[0].activity is None
    assert net.transitions[0].activity == "Ship"
    with pytest.raises(ValueError):
        hide_ocpn(net, ObjectHidingSpec(("no",)))


def test_ancestor_descendant_subnets_are_structural_and_directional():
    net = series()
    ancestors = object_subnet(net, ObjectSubnetSpec(("tau",), "ancestors", False)).value
    assert ancestors.node_ids == ("a", "p", "start")
    descendants = object_subnet(
        net, ObjectSubnetSpec(("tau",), "descendants", False)
    ).value
    assert descendants.node_ids == ("b", "end", "q")
    assert "not_executable" in ancestors.meaning
    with pytest.raises(ValueError):
        object_subnet(net, ObjectSubnetSpec(("unknown",)))


def test_series_reduction_preserves_visible_object_language_and_marks():
    net = series()
    result = reduce_ocpn(net, ObjectReductionSpec(rules=("series_places",)))
    assert result.status is ComputeStatus.COMPUTED
    assert len(result.value.steps) == 1
    assert result.value.steps[0].removed_transition_ids == ("tau",)
    assert dict(result.value.original_to_reduced_places)["p"] == "q"
    assert brute_language(net) == brute_language(result.value.model)
    assert result.value.model.initial_marking == net.initial_marking
    assert result.value.model.final_marking == net.final_marking


def test_series_reduction_transfers_initial_p_tokens_and_forbids_unsafe_boundaries():
    base = series()
    starting_inside = replace(base, initial_marking=marking(("p", "x")))
    reduced = reduce_ocpn(
        starting_inside, ObjectReductionSpec(rules=("series_places",))
    ).value
    assert reduced.model.initial_marking == marking(("q", "x"))
    assert brute_language(starting_inside) == brute_language(reduced.model)
    q_initial = replace(base, initial_marking=marking(("q", "x")))
    p_final = replace(base, final_marking=marking(("p", "x")))
    assert not reduce_ocpn(
        q_initial, ObjectReductionSpec(rules=("series_places",))
    ).value.steps
    assert not reduce_ocpn(
        p_final, ObjectReductionSpec(rules=("series_places",))
    ).value.steps
    assert not reduce_ocpn(
        series(variable=True), ObjectReductionSpec(rules=("series_places",))
    ).value.steps
    assert not reduce_ocpn(
        base, ObjectReductionSpec(rules=("series_places",), sacred_node_ids=("tau",))
    ).value.steps


def parallel_places(*, mismatch=False):
    return ObjectCentricPetriNet(
        tuple(TypedPlace(p, "item") for p in ("p", "q", "end")),
        (Transition("a", "A"),),
        (ObjectArc("p", "a"), ObjectArc("q", "a"), ObjectArc("a", "end")),
        marking(("p", "x"), ("q", "y" if mismatch else "x")),
        marking(("end", "x")),
        (("x", "item"), ("y", "item")),
    )


def test_parallel_place_rule_checks_object_identity_not_just_token_count():
    net = parallel_places()
    reduced = reduce_ocpn(net, ObjectReductionSpec(rules=("parallel_places",))).value
    assert len(reduced.steps) == 1
    assert reduced.model.initial_marking == marking(("p", "x"))
    assert brute_language(net) == brute_language(reduced.model)
    mismatch = parallel_places(mismatch=True)
    assert not reduce_ocpn(
        mismatch, ObjectReductionSpec(rules=("parallel_places",))
    ).value.steps
    assert brute_language(mismatch) == set()


def test_parallel_places_require_equal_final_multisets_and_protect_sacred_nodes():
    net = parallel_places()
    unequal_final = replace(net, final_marking=marking(("p", "x")))
    assert not reduce_ocpn(
        unequal_final, ObjectReductionSpec(rules=("parallel_places",))
    ).value.steps
    sacred = reduce_ocpn(
        net, ObjectReductionSpec(rules=("parallel_places",), sacred_node_ids=("q",))
    ).value
    assert sacred.steps[0].removed_place_ids == ("p",)
    assert {p.id for p in sacred.model.places} == {"q", "end"}


def test_parallel_transitions_require_same_activity_and_full_cardinality_policy():
    net = shipping()
    duplicate = replace(
        net,
        transitions=net.transitions + (Transition("ship2", "Ship"),),
        arcs=net.arcs
        + tuple(
            replace(
                a,
                source="ship2" if a.source == "ship" else a.source,
                target="ship2" if a.target == "ship" else a.target,
            )
            for a in net.arcs
        ),
    )
    reduced = reduce_ocpn(
        duplicate, ObjectReductionSpec(rules=("parallel_transitions",))
    ).value
    assert len(reduced.steps) == 1
    assert brute_language(duplicate) == brute_language(reduced.model)
    other_label = replace(
        duplicate,
        transitions=(Transition("ship", "Ship"), Transition("ship2", "Other")),
    )
    assert not reduce_ocpn(
        other_label, ObjectReductionSpec(rules=("parallel_transitions",))
    ).value.steps


def test_silent_loop_removal_changes_divergence_but_not_visible_language():
    net = series()
    loop = replace(
        net,
        transitions=net.transitions + (Transition("loop"),),
        arcs=net.arcs + (ObjectArc("start", "loop"), ObjectArc("loop", "start")),
    )
    reduced = reduce_ocpn(loop, ObjectReductionSpec(rules=("silent_self_loop",))).value
    assert len(reduced.steps) == 1
    assert "silent_divergence" in reduced.not_preserved
    assert brute_language(loop) == brute_language(reduced.model)


def test_reduction_limit_reports_remaining_work_without_invalidating_result():
    net = series()
    loop = replace(
        net,
        transitions=net.transitions + (Transition("loop"), Transition("loop2")),
        arcs=net.arcs
        + (
            ObjectArc("start", "loop"),
            ObjectArc("loop", "start"),
            ObjectArc("end", "loop2"),
            ObjectArc("loop2", "end"),
        ),
    )
    result = reduce_ocpn(
        loop, ObjectReductionSpec(rules=("silent_self_loop",), max_steps=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert not result.value.fixed_point_reached and len(result.value.steps) == 1
    assert brute_language(loop) == brute_language(result.value.model)


def test_per_object_invariants_hold_for_every_shipping_subset():
    net = shipping()
    result = object_place_invariants(net).value
    assert len(result.by_object_type) == 2
    assert all(row.conservation_compatible_with_final for row in result.by_object_type)
    for ids in (("i1",), ("i2",), ("i1", "i2")):
        following = fire_binding(
            net,
            net.initial_marking,
            Binding("ship", (("item", ids), ("order", ("o",)))),
        )
        values = object_place_invariants(replace(net, final_marking=following)).value
        assert all(
            row.conservation_compatible_with_final for row in values.by_object_type
        )
    impossible = object_place_invariants(
        replace(net, final_marking=marking(("od", "o"), ("id", "i1")))
    ).value
    assert not next(
        row for row in impossible.by_object_type if row.object_type == "item"
    ).conservation_compatible_with_final
    with pytest.raises(ValueError):
        object_place_invariants(net, ObjectInvariantSpec(("missing",)))


def test_joint_soundness_finds_partial_shipping_deadlocks_despite_type_invariants():
    net = shipping()
    result = analyze_ocpn_soundness(net)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.assessment == "disproven"
    assert result.value.option_to_complete is False
    assert len(result.value.observed_deadlock_state_ids) == 2
    assert result.value.accepting_state is not None
    assert result.value.global_all_object_universes_soundness is None
    assert all(
        row.conservation_compatible_with_final
        for row in object_place_invariants(net).value.by_object_type
    )


def test_soundness_proves_only_declared_universe_and_detects_nonterminating_component():
    net = series()
    report = analyze_ocpn_soundness(net).value
    assert report.assessment == "proven" and report.exploration_complete
    assert (
        report.option_to_complete
        and report.proper_completion
        and report.no_dead_transitions
    )
    assert report.scope == "declared_finite_object_universe"
    trapped = replace(
        net,
        arcs=tuple(a for a in net.arcs if a.source != "a") + (ObjectArc("a", "start"),),
    )
    value = analyze_ocpn_soundness(trapped).value
    assert value.assessment == "disproven" and value.option_to_complete is False
    assert value.observed_deadlock_state_ids == ()
    assert value.noncompletable_state_ids == (0,)


def test_soundness_caps_are_unknown_not_false_success_or_dead_transitions():
    report = analyze_ocpn_soundness(series(), ObjectSoundnessSpec(max_states=1))
    assert report.status is ComputeStatus.PARTIAL
    assert report.value.assessment == "unknown"
    assert (
        report.value.option_to_complete is None
        and report.value.dead_transition_ids == ()
    )
    report = analyze_ocpn_soundness(
        shipping(), ObjectSoundnessSpec(max_bindings_per_marking=1)
    )
    assert report.status is ComputeStatus.PARTIAL
    assert (
        report.value.assessment == "disproven"
    )  # one actual nonfinal deadlock was reached
    assert report.value.no_dead_transitions is None


def test_unbounded_growth_is_unknown_with_an_observed_improper_completion_counterexample():
    net = ObjectCentricPetriNet(
        (TypedPlace("p", "item"),),
        (Transition("new", "Produce"),),
        (ObjectArc("new", "p"),),
        ObjectMarking(),
        marking(("p", "x")),
        (("x", "item"),),
    )
    report = analyze_ocpn_soundness(net, ObjectSoundnessSpec(max_states=4)).value
    assert not report.exploration_complete
    assert report.assessment == "disproven" and report.proper_completion is False
    assert report.option_to_complete is None
    empty_final = replace(series(), final_marking=ObjectMarking())
    assert analyze_ocpn_soundness(empty_final).value.proper_completion is None


def test_causal_conversion_preserves_joint_binding_and_initial_final_markings():
    source = shipping()
    conversion = ocpn_to_causal_net(source).value
    causal = conversion.causal_net
    assert conversion.exact and not conversion.loss_report
    assert (
        causal.initial_marking == source.initial_marking
        and causal.final_marking == source.final_marking
    )
    enumeration = enumerate_enabled_causal_bindings(
        causal, causal.initial_marking, max_bindings=10
    )
    assert enumeration.complete and enumeration.candidate_count == 3
    full = next(
        binding
        for binding in enumeration.bindings
        if len(dict(binding.consumed)["ir"]) == 2
    )
    assert (
        fire_causal_binding(causal, causal.initial_marking, full)
        == causal.final_marking
    )
    assert causal_firing_objects(causal, full) == (
        ("i1", "item"),
        ("i2", "item"),
        ("o", "order"),
    )
    back = causal_net_to_ocpn(causal).value
    assert back.exact and back.ocpn == source


def test_ocpn_choice_place_conversion_refuses_without_erasing_choice():
    source = series()
    source = replace(
        source,
        transitions=source.transitions + (Transition("other", "Other"),),
        arcs=source.arcs + (ObjectArc("start", "other"), ObjectArc("other", "end")),
    )
    result = ocpn_to_causal_net(source)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.causal_net is None and not result.value.exact
    assert any(
        "multiple producer/consumer" in reason
        for reason in result.value.refusal_reasons
    )


def test_native_causal_split_routes_different_objects_without_conversion_alias():
    net = split_causal()
    choices = enumerate_enabled_causal_bindings(
        net, net.initial_marking, max_bindings=10
    )
    assert choices.complete and choices.candidate_count == 2
    expected = {(("l", ("x",)), ("r", ("y",))), (("l", ("y",)), ("r", ("x",)))}
    assert {binding.produced for binding in choices.bindings} == expected
    selected = next(
        binding for binding in choices.bindings if dict(binding.produced)["l"] == ("x",)
    )
    state = fire_causal_binding(net, net.initial_marking, selected)
    for transition in ("left", "right"):
        enabled = enumerate_enabled_causal_bindings(net, state, max_bindings=10)
        binding = next(
            binding
            for binding in enabled.bindings
            if binding.transition_id == transition
        )
        state = fire_causal_binding(net, state, binding)
    assert state == net.final_marking
    conversion = causal_net_to_ocpn(net).value
    assert not conversion.exact and conversion.ocpn is None
    assert any("disjoint" in reason for reason in conversion.refusal_reasons)


def test_causal_equality_disjointness_and_object_conservation_are_actual_constraints():
    net = split_causal()
    overlap = CausalFiring(
        "split", "si", "so", (("entry", ("x", "y")),), (("l", ("x",)), ("r", ("x",)))
    )
    assert not is_causal_binding_enabled(net, net.initial_marking, overlap)
    with pytest.raises(ValueError, match="not enabled"):
        fire_causal_binding(net, net.initial_marking, overlap)
    equal = split_causal(disjoint=False, equality=True)
    assert (
        enumerate_enabled_causal_bindings(
            equal, equal.initial_marking, max_bindings=10
        ).candidate_count
        == 0
    )
    single = replace(
        equal,
        objects=(("x", "item"),),
        initial_marking=marking(("entry", "x")),
        final_marking=marking(("lend", "x"), ("rend", "x")),
        input_bindings=(
            replace(equal.input_bindings[2], markers=(CausalMarker("entry"),)),
            *equal.input_bindings[:2],
        ),
    )
    choices = enumerate_enabled_causal_bindings(
        single, single.initial_marking, max_bindings=10
    )
    assert choices.candidate_count == 1
    assert choices.bindings[0].produced == (("l", ("x",)), ("r", ("x",)))


def test_zero_cardinality_participation_is_explicit_and_no_obligation_is_invented():
    base = causal_shipping()
    zero_groups = []
    for group in base.input_bindings + base.output_bindings:
        zero_groups.append(
            replace(
                group,
                markers=tuple(
                    replace(marker, min_objects=0, max_objects=0)
                    for marker in group.markers
                ),
            )
        )
    net = replace(
        base,
        input_bindings=(zero_groups[0],),
        output_bindings=(zero_groups[1],),
        initial_marking=ObjectMarking(),
        final_marking=ObjectMarking(),
    )
    choices = enumerate_enabled_causal_bindings(
        net, net.initial_marking, max_bindings=10
    )
    assert choices.complete and choices.candidate_count == 1
    assert choices.bindings[0].consumed == (("ir", ()), ("or", ()))
    assert (
        fire_causal_binding(net, net.initial_marking, choices.bindings[0])
        == ObjectMarking()
    )
    assert causal_firing_objects(net, choices.bindings[0]) == ()


def test_causal_binding_count_and_candidate_limit_are_distinct():
    net = causal_shipping()
    only_count = enumerate_enabled_causal_bindings(
        net, net.initial_marking, max_bindings=0
    )
    assert (
        only_count.bindings == ()
        and only_count.candidate_count == 3
        and not only_count.complete
    )
    capped = enumerate_enabled_causal_bindings(
        net, net.initial_marking, max_bindings=10, max_candidates=1
    )
    assert (
        capped.candidate_count is None
        and not capped.complete
        and capped.examined_candidates == 1
    )
    exact = enumerate_enabled_causal_bindings(net, net.initial_marking, max_bindings=3)
    assert exact.complete
    at_exact_budget = enumerate_enabled_causal_bindings(
        net,
        net.initial_marking,
        max_bindings=3,
        max_candidates=exact.examined_candidates,
    )
    assert at_exact_budget == exact
    with pytest.raises(ValueError):
        enumerate_enabled_causal_bindings(
            net, net.initial_marking, max_bindings=0, max_candidates=0
        )


def test_empty_later_marker_domain_never_enumerates_an_earlier_powerset():
    # Regression for the review counterexample: 2**60 partial assignments
    # would yield no complete candidate, silently bypassing max_candidates.
    objects = tuple((f"o{i:02}", "item") for i in range(60))
    net = ObjectCentricCausalNet(
        (Transition("t", "T"),),
        (CausalChannel("a", "item", None, "t"), CausalChannel("z", "item", None, "t")),
        (
            CausalMarkerGroup(
                "in", "t", (CausalMarker("a", 0, None), CausalMarker("z", 1, 1))
            ),
        ),
        (CausalMarkerGroup("out", "t", ()),),
        marking(*(("a", obj) for obj, _ in objects)),
        ObjectMarking(),
        objects,
    )
    with patch(
        "pix.object_centric.models.combinations",
        side_effect=AssertionError("must precheck empty domains"),
    ):
        result = enumerate_enabled_causal_bindings(
            net, net.initial_marking, max_bindings=1, max_candidates=1
        )
    assert (
        result.complete
        and result.candidate_count == 0
        and result.examined_candidates == 0
    )


def test_causal_token_multiplicity_is_preserved_and_firings_do_not_repeat_ids():
    net = causal_shipping()
    state = ObjectMarking(net.initial_marking.tokens + net.initial_marking.tokens)
    choice = next(
        binding
        for binding in enumerate_enabled_causal_bindings(
            net, state, max_bindings=10
        ).bindings
        if len(dict(binding.consumed)["ir"]) == 2
    )
    following = fire_causal_binding(net, state, choice)
    assert following == ObjectMarking(
        net.initial_marking.tokens + net.final_marking.tokens
    )
    with pytest.raises(ValueError):
        replace(choice, consumed=(("ir", ("i1", "i1")), ("or", ("o",))))
    with pytest.raises(ValueError, match="undeclared"):
        fire_causal_binding(
            net, state, replace(choice, consumed=(("ir", ("missing",)), ("or", ("o",))))
        )


def test_causal_alternative_unfolding_is_exact_and_reports_identity_mapping():
    net = causal_shipping()
    original = net.input_bindings[0]
    alternate = replace(
        original,
        id="alternative",
        markers=tuple(
            replace(marker, min_objects=2, max_objects=2)
            if marker.channel_id == "ir"
            else marker
            for marker in original.markers
        ),
    )
    net = replace(net, input_bindings=(original, alternate))
    result = causal_net_to_ocpn(net).value
    assert result.exact and len(result.ocpn.transitions) == 2
    assert dict(result.transition_mapping)["ship"] == ("causal:ship:0", "causal:ship:1")
    assert result.loss_report and "group IDs" in result.loss_report[0]
    assert brute_language(result.ocpn) == brute_language(shipping())
    capped = causal_net_to_ocpn(
        net, ObjectConversionSpec(max_transition_copies=1)
    ).value
    assert capped.ocpn is None and not capped.exact


def test_conversion_rejects_independent_same_type_objects_not_fake_interval_merge():
    net = split_causal(disjoint=False)
    result = causal_net_to_ocpn(net).value
    assert not result.exact
    assert any(
        "independent object selections" in reason for reason in result.refusal_reasons
    )


@pytest.mark.parametrize(
    "change",
    [
        {"objects": (("x", "item"), ("x", "item"))},
        {"input_bindings": ()},
        {"channels": (CausalChannel("bad", "item", "missing", None),)},
        {"initial_marking": marking(("unknown", "i1"))},
        {"initial_marking": marking(("ir", "o"))},
    ],
)
def test_causal_model_rejects_invalid_structure(change):
    with pytest.raises((TypeError, ValueError)):
        replace(causal_shipping(), **change)


def test_models_immutable_and_identity_includes_marker_constraints_and_boundaries():
    net = causal_shipping()
    with pytest.raises(FrozenInstanceError):
        net.objects = ()
    assert causal_net_digest(
        replace(net, transitions=tuple(reversed(net.transitions)))
    ) == causal_net_digest(net)
    assert causal_net_digest(
        replace(net, initial_marking=net.final_marking)
    ) != causal_net_digest(net)
    first = split_causal()
    assert causal_net_digest(first) != causal_net_digest(split_causal(disjoint=False))


@pytest.mark.parametrize(
    "call",
    [
        lambda: project_ocpn(shipping(), ObjectProjectionSpec(object_types=("item",))),
        lambda: hide_ocpn(shipping(), ObjectHidingSpec(("ship",))),
        lambda: object_subnet(series(), ObjectSubnetSpec(("tau",))),
        lambda: reduce_ocpn(series()),
        lambda: object_place_invariants(shipping()),
        lambda: analyze_ocpn_soundness(shipping()),
        lambda: ocpn_to_causal_net(shipping()),
        lambda: causal_net_to_ocpn(causal_shipping()),
        lambda: causal_net_to_ocpn(split_causal()),
    ],
)
def test_every_operator_result_roundtrips_with_finite_nested_evidence(call):
    from pix import results

    value = call()
    with patch.object(results, "_schemas", return_value=RESULT_SCHEMAS):
        restored = results.result_from_json(results.result_json_bytes(value))
    assert restored == value


def test_requests_distinguish_scope_and_preserve_source_identity():
    net = shipping()
    whole = project_ocpn(net)
    item = project_ocpn(net, ObjectProjectionSpec(object_types=("item",)))
    assert (
        whole.source_digest == item.source_digest
        and whole.computation_id != item.computation_id
    )
    assert whole == project_ocpn(net)
