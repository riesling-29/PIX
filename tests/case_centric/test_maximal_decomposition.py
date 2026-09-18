"""Independent ownership, finest-partition and synchronized firing checks."""

from collections import Counter
from dataclasses import FrozenInstanceError, dataclass, replace
from itertools import product

import pytest

from pix.case_centric.maximal_decomposition import (
    MaximalDecompositionRequest,
    MaximalDecompositionSpec,
    MaximalModelDecomposition,
    MaximalRecompositionRequest,
    maximal_decompose_model,
    recompose_maximal_decomposition,
    validate_maximal_decomposition_result,
)
from pix.case_centric.model_analysis import decompose_model
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def net(places, transitions, arcs, initial=(), final=()):
    return PetriNet(
        tuple(Place(p) for p in places),
        tuple(Transition(*t) for t in transitions),
        tuple(Arc(*a) for a in arcs),
        Marking(initial),
        Marking(final),
    )


def sequence():
    return net(
        "smf",
        (("a", "A"), ("b", "B")),
        (("s", "a"), ("a", "m"), ("m", "b"), ("b", "f")),
        (("s", 1),),
        (("f", 1),),
    )


def choice():
    return net(
        "sf",
        (("a", "A"), ("b", "B")),
        (("s", "a"), ("a", "f"), ("s", "b"), ("b", "f")),
        (("s", 1),),
        (("f", 1),),
    )


def concurrent():
    return net(
        ("s", "left", "right", "left_done", "right_done", "f"),
        (("fork", "Fork"), ("a", "A"), ("b", "B"), ("join", "Join")),
        (
            ("s", "fork"),
            ("fork", "left"),
            ("fork", "right"),
            ("left", "a"),
            ("a", "left_done"),
            ("right", "b"),
            ("b", "right_done"),
            ("left_done", "join"),
            ("right_done", "join"),
            ("join", "f"),
        ),
        (("s", 1),),
        (("f", 1),),
    )


def silent_block():
    return net(
        "sxyzf",
        (("a", "A"), ("tau", None), ("b", "B")),
        (
            ("s", "a"),
            ("a", "x"),
            ("x", "tau"),
            ("tau", "y"),
            ("tau", "z"),
            ("y", "b"),
            ("z", "b"),
            ("b", "f"),
        ),
        (("s", 2),),
        (("f", 2),),
    )


def duplicate_choice():
    return net(
        "sxyf",
        (("a1", "A"), ("a2", "A"), ("b", "B")),
        (
            ("s", "a1"),
            ("a1", "x"),
            ("x", "b"),
            ("s", "a2"),
            ("a2", "y"),
            ("y", "b"),
            ("b", "f"),
        ),
        (("s", 1),),
        (("f", 1),),
    )


def parent(value, status=ComputeStatus.COMPUTED, source="source-log", issues=()):
    if status is not ComputeStatus.COMPUTED and not issues:
        issues = (ComputeIssue("upstream_coverage", "upstream is incomplete"),)
    return ComputationResult(
        "fixture",
        "1.0.0",
        source,
        MaximalDecompositionSpec(),
        status,
        value,
        issues,
        "parent-id" if source else None,
    )


def independently_enabled(model, marking, transition_id):
    counts = dict(marking.tokens)
    return all(
        counts.get(a.source, 0) >= a.weight
        for a in model.arcs
        if a.target == transition_id
    )


def independently_fire(model, marking, transition_id):
    counts = Counter(dict(marking.tokens))
    assert independently_enabled(model, marking, transition_id)
    for arc in model.arcs:
        if arc.target == transition_id:
            counts[arc.source] -= arc.weight
        if arc.source == transition_id:
            counts[arc.target] += arc.weight
    return Marking(tuple((p, count) for p, count in counts.items() if count))


@pytest.mark.parametrize(
    "factory, expected",
    [
        (sequence, 3),
        (choice, 2),
        (concurrent, 6),
        (silent_block, 3),
        (duplicate_choice, 2),
    ],
)
def test_connected_nets_are_split_without_losing_exact_accepting_structure(
    factory, expected
):
    model = factory()
    assert len(decompose_model(model).value.components) == 1
    result = maximal_decompose_model(model)
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    assert len(value.components) == expected
    assert value.certificate.identical_structure
    assert value.certificate.identical_markings
    assert value.certificate.source_model_digest == model_digest(model)
    assert value.certificate.recomposed_model_digest == model_digest(model)
    assert value.certificate.source_initial_marking == model.initial_marking
    assert value.certificate.source_final_marking == model.final_marking
    assert value.reference_equivalence == "unverified"
    rebuilt = recompose_maximal_decomposition(result)
    assert rebuilt.status is ComputeStatus.COMPUTED
    assert rebuilt.value == model
    assert rebuilt.parent_computation_ids == (result.computation_id,)
    assert rebuilt.source_digest == result.source_digest
    assert recompose_maximal_decomposition(value).value == model


@pytest.mark.parametrize(
    "factory", [sequence, choice, concurrent, silent_block, duplicate_choice]
)
def test_place_arc_marking_ownership_is_exact_and_replica_ids_are_retained(factory):
    model = factory()
    value = maximal_decompose_model(model).value
    assert Counter(p.id for c in value.components for p in c.model.places) == Counter(
        p.id for p in model.places
    )
    assert Counter(a for c in value.components for a in c.model.arcs) == Counter(
        model.arcs
    )
    assert Counter(
        row for c in value.components for row in c.model.initial_marking.tokens
    ) == Counter(model.initial_marking.tokens)
    assert Counter(
        row for c in value.components for row in c.model.final_marking.tokens
    ) == Counter(model.final_marking.tokens)
    assert set(value.place_ownership) == {
        (p.id, c.component_id) for c in value.components for p in c.model.places
    }
    assert {(row.arc, row.component_id) for row in value.arc_ownership} == {
        (a, c.component_id) for c in value.components for a in c.model.arcs
    }
    labels = Counter(t.activity for t in model.transitions if t.activity is not None)
    for t in model.transitions:
        owners = tuple(
            c.component_id for c in value.components if t in c.model.transitions
        )
        assert owners
        if t.activity is None or labels[t.activity] > 1:
            assert len(owners) == 1
        if len(owners) > 1:
            shared = next(
                row for row in value.shared_transitions if row.transition_id == t.id
            )
            assert shared.activity == t.activity
            assert shared.component_ids == owners
    for c in value.components:
        assert set(c.internal_transition_ids).isdisjoint(c.boundary_transition_ids)
        assert set(c.internal_transition_ids) | set(c.boundary_transition_ids) == {
            t.id for t in c.model.transitions
        }


def test_duplicate_label_peers_merge_even_when_original_graph_is_disconnected():
    model = net(
        "pqrs",
        (("a1", "A"), ("a2", "A"), ("b1", "B"), ("b2", "B")),
        (("p", "a1"), ("q", "a2"), ("r", "b1"), ("s", "b2")),
    )
    result = maximal_decompose_model(model)
    assert len(decompose_model(model).value.components) == 4
    assert len(result.value.components) == 2
    assert {
        frozenset(t.id for t in c.model.transitions) for c in result.value.components
    } == {frozenset(("a1", "a2")), frozenset(("b1", "b2"))}
    assert recompose_maximal_decomposition(result).value == model


def test_labels_cannot_collide_with_unrelated_node_ids():
    model = net(
        ("A", "B"),
        (("left", "A"), ("right", "A")),
        (("A", "left"), ("B", "right")),
        (("A", 3),),
        (("B", 2),),
    )
    result = maximal_decompose_model(model)
    assert len(result.value.components) == 1
    assert recompose_maximal_decomposition(result).value == model


def test_silent_transition_incidence_stays_in_one_component():
    value = maximal_decompose_model(silent_block()).value
    component = next(c for c in value.components if "tau" in c.internal_transition_ids)
    assert {p.id for p in component.model.places} == set("xyz")
    assert "tau" not in {row.transition_id for row in value.shared_transitions}


@pytest.mark.parametrize(
    "factory", [sequence, choice, concurrent, silent_block, duplicate_choice]
)
def test_synchronized_local_firing_equals_global_firing_at_all_binary_markings(factory):
    """Token equations checked even at unreachable markings, without PIX firing."""
    model = factory()
    parts = maximal_decompose_model(model).value.components
    for counts in product(range(2), repeat=len(model.places)):
        marking = Marking(tuple((p.id, n) for p, n in zip(model.places, counts) if n))
        locals_ = tuple(
            Marking(
                tuple(
                    row
                    for row in marking.tokens
                    if row[0] in {p.id for p in c.model.places}
                )
            )
            for c in parts
        )
        for transition in model.transitions:
            participants = [
                i for i, c in enumerate(parts) if transition in c.model.transitions
            ]
            local_enabled = all(
                independently_enabled(parts[i].model, locals_[i], transition.id)
                for i in participants
            )
            assert local_enabled == independently_enabled(model, marking, transition.id)
            if local_enabled:
                after = tuple(
                    independently_fire(c.model, local, transition.id)
                    if i in participants
                    else local
                    for i, (c, local) in enumerate(zip(parts, locals_))
                )
                recombined = Marking(
                    tuple(row for local in after for row in local.tokens)
                )
                assert recombined == independently_fire(model, marking, transition.id)


@pytest.mark.parametrize(
    "word", [("fork", "a", "b", "join"), ("fork", "b", "a", "join")]
)
def test_concurrent_token_flow_reaches_exact_global_final_marking(word):
    model = concurrent()
    parts = maximal_decompose_model(model).value.components
    marking, local_markings = (
        model.initial_marking,
        [c.model.initial_marking for c in parts],
    )
    for transition_id in word:
        marking = independently_fire(model, marking, transition_id)
        for i, c in enumerate(parts):
            if any(t.id == transition_id for t in c.model.transitions):
                local_markings[i] = independently_fire(
                    c.model, local_markings[i], transition_id
                )
        assert (
            Marking(tuple(row for local in local_markings for row in local.tokens))
            == marking
        )
    assert marking == model.final_marking
    assert local_markings == [c.model.final_marking for c in parts]


def partitions(items):
    if not items:
        yield ()
        return
    first, *remaining = items
    for partition in partitions(remaining):
        yield ((first,),) + partition
        for i, block in enumerate(partition):
            yield partition[:i] + ((first,) + block,) + partition[i + 1 :]


@pytest.mark.parametrize("labels", [("A", "B"), ("A", "A"), (None, "A"), (None, None)])
def test_finest_partition_matches_exhaustive_valid_partitions_on_small_nets(labels):
    """Independent enumeration of all five partitions of three places."""
    places = ("p", "q", "r")
    for left, right in product(range(1, 8), repeat=2):
        arcs = tuple(
            (p, t)
            for t, mask in (("t1", left), ("t2", right))
            for i, p in enumerate(places)
            if mask & (1 << i)
        )
        model = net(places, tuple(zip(("t1", "t2"), labels)), arcs)
        valid_sizes = []
        for partition in partitions(places):
            owner = {p: i for i, block in enumerate(partition) for p in block}
            memberships = {
                t.id: {owner[a.source] for a in model.arcs if a.target == t.id}
                for t in model.transitions
            }
            counts = Counter(label for label in labels if label is not None)
            valid = True
            for t in model.transitions:
                if (t.activity is None or counts[t.activity] > 1) and len(
                    memberships[t.id]
                ) != 1:
                    valid = False
            for label, count in counts.items():
                if (
                    count > 1
                    and len(
                        set().union(
                            *(
                                memberships[t.id]
                                for t in model.transitions
                                if t.activity == label
                            )
                        )
                    )
                    != 1
                ):
                    valid = False
            if valid:
                valid_sizes.append(len(partition))
        actual = maximal_decompose_model(model).value
        assert len(actual.components) == max(valid_sizes)


def test_isolated_nodes_and_empty_net_are_preserved_as_explicit_extension():
    model = net(
        ("alone",),
        (("tau", None), ("unique", "U"), ("dup1", "D"), ("dup2", "D")),
        (),
        (("alone", 4),),
        (("alone", 2),),
    )
    result = maximal_decompose_model(model)
    assert len(result.value.components) == 4
    assert recompose_maximal_decomposition(result).value == model
    empty = net((), (), ())
    result = maximal_decompose_model(empty)
    assert result.value.components == ()
    assert recompose_maximal_decomposition(result).value == empty


def test_self_loop_owns_both_arcs_and_marking_token_multiplicity():
    model = net("p", (("a", "A"),), (("p", "a"), ("a", "p")), (("p", 7),), (("p", 7),))
    result = maximal_decompose_model(model)
    assert len(result.value.components) == 1
    assert len(result.value.arc_ownership) == 2
    assert recompose_maximal_decomposition(result).value == model


@pytest.mark.parametrize("weight", [2, 100])
def test_weighted_profile_is_unavailable_without_silently_losing_weights(weight):
    model = net("p", (("a", "A"),), (("p", "a", weight),), (("p", weight),))
    result = maximal_decompose_model(model)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.source_digest == model_digest(model)
    assert result.issues[-1].code == "weighted_decomposition_unsupported"


@pytest.mark.parametrize(
    "spec",
    [MaximalDecompositionSpec(max_nodes=1), MaximalDecompositionSpec(max_arcs=1)],
)
def test_budget_never_releases_incomplete_partition(spec):
    result = maximal_decompose_model(sequence(), spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[-1].code == "decomposition_budget_exceeded"


@pytest.mark.parametrize("field", ["max_nodes", "max_arcs"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "3"])
def test_invalid_budgets(field, value):
    with pytest.raises(ValueError):
        MaximalDecompositionSpec(**{field: value})


def test_request_provenance_partial_coverage_and_model_digest_are_not_lost():
    upstream = parent(sequence(), ComputeStatus.PARTIAL)
    result = maximal_decompose_model(upstream)
    assert result.status is ComputeStatus.PARTIAL
    assert result.source_digest == "source-log"
    assert result.parent_computation_ids == ("parent-id",)
    assert result.issues == upstream.issues
    assert result.spec.model_digest == model_digest(sequence())
    assert (
        result.computation_id
        != maximal_decompose_model(
            parent(choice(), ComputeStatus.PARTIAL)
        ).computation_id
    )
    recomposed = recompose_maximal_decomposition(result)
    assert recomposed.status is ComputeStatus.PARTIAL
    assert recomposed.value == sequence()
    assert recomposed.issues == result.issues


@pytest.mark.parametrize(
    "status", [ComputeStatus.UNAVAILABLE, ComputeStatus.INVALID_INPUT]
)
@pytest.mark.parametrize("source", [None, "source-log"])
def test_failed_parent_is_preserved(status, source):
    upstream = parent(None, status, source)
    result = maximal_decompose_model(upstream)
    assert result.status is status
    assert result.source_digest == source
    assert result.issues == upstream.issues
    assert result.value is None
    rebuilt = recompose_maximal_decomposition(result)
    assert rebuilt.status is status
    assert rebuilt.value is None


@pytest.mark.parametrize("value", ["not a net", 1, ("wrong",)])
def test_other_computed_model_classes_have_explicit_unsupported_issue(value):
    result = maximal_decompose_model(parent(value))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == "decomposition_model_class_unsupported"


def test_native_net_subclass_does_not_silently_lose_extended_semantics():
    class ExtendedNet(PetriNet):
        pass

    model = sequence()
    result = maximal_decompose_model(
        ExtendedNet(
            model.places,
            model.transitions,
            model.arcs,
            model.initial_marking,
            model.final_marking,
        )
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == "decomposition_model_class_unsupported"


@pytest.mark.parametrize("value", [None, {}, 12, "PNML"])
def test_untyped_input_raises(value):
    with pytest.raises(TypeError):
        maximal_decompose_model(value)
    with pytest.raises(TypeError):
        recompose_maximal_decomposition(value)


def test_invalid_spec_and_immutable_records():
    with pytest.raises(TypeError):
        maximal_decompose_model(sequence(), {})
    result = maximal_decompose_model(sequence())
    with pytest.raises(FrozenInstanceError):
        result.value.profile = "changed"
    with pytest.raises(FrozenInstanceError):
        result.value.components[0].component_id = "changed"


def test_forged_input_records_are_revalidated():
    model = sequence()
    object.__setattr__(model.arcs[0], "weight", 0)
    result = maximal_decompose_model(model)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


@pytest.mark.parametrize(
    "field, replacement",
    [
        ("place_ownership", ()),
        ("arc_ownership", ()),
        ("shared_transitions", ()),
        ("profile", "unknown"),
        ("composition", "independent_shuffle_product"),
        ("maximality", "arbitrary"),
        ("source_model_digest", "wrong"),
    ],
)
def test_recomposition_rejects_altered_ownership_or_claims(field, replacement):
    value = maximal_decompose_model(sequence()).value
    result = recompose_maximal_decomposition(replace(value, **{field: replacement}))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[-1].code == "invalid_decomposition_certificate"
    assert result.value is None


@pytest.mark.parametrize(
    "change",
    [
        "missing_component",
        "duplicate_component",
        "changed_marking",
        "changed_replica_label",
        "false_certificate",
        "forged_marking_witness",
    ],
)
def test_recomposition_rejects_structural_or_marking_tampering(change):
    value = maximal_decompose_model(sequence()).value
    if change == "missing_component":
        value = replace(value, components=value.components[1:])
    elif change == "duplicate_component":
        value = replace(value, components=value.components + (value.components[0],))
    elif change == "changed_marking":
        index = next(
            i for i, c in enumerate(value.components) if c.model.initial_marking.tokens
        )
        component = value.components[index]
        altered = replace(
            component, model=replace(component.model, initial_marking=Marking())
        )
        value = replace(
            value,
            components=value.components[:index]
            + (altered,)
            + value.components[index + 1 :],
        )
    elif change == "changed_replica_label":
        component = value.components[0]
        altered = replace(
            component,
            model=replace(
                component.model,
                transitions=(
                    replace(component.model.transitions[0], activity="changed"),
                ),
            ),
        )
        value = replace(value, components=(altered,) + value.components[1:])
    elif change == "false_certificate":
        value = replace(
            value, certificate=replace(value.certificate, identical_structure=False)
        )
    else:
        value = replace(
            value,
            certificate=replace(value.certificate, source_final_marking=Marking()),
        )
    result = recompose_maximal_decomposition(value)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


def test_wrong_recomposition_parent_payload_is_invalid():
    result = recompose_maximal_decomposition(parent(sequence()))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[-1].code == "invalid_decomposition_payload"


def test_deterministic_results_and_request_records():
    first, second = (
        maximal_decompose_model(concurrent()),
        maximal_decompose_model(concurrent()),
    )
    assert first == second
    assert isinstance(first.spec, MaximalDecompositionRequest)
    rebuilt = recompose_maximal_decomposition(first)
    assert isinstance(rebuilt.spec, MaximalRecompositionRequest)
    assert rebuilt.spec.decomposition == first.value


def test_nested_payload_codec_roundtrip():
    from pix.results import _decode, _encode

    result = maximal_decompose_model(duplicate_choice())
    assert _decode(_encode(result.spec), MaximalDecompositionRequest) == result.spec
    assert _decode(_encode(result.value), MaximalModelDecomposition) == result.value
    rebuilt = recompose_maximal_decomposition(result)
    assert _decode(_encode(rebuilt.spec), MaximalRecompositionRequest) == rebuilt.spec
    assert _decode(_encode(rebuilt.value), PetriNet) == rebuilt.value


def test_discovered_model_wrapper_preserves_parent_identity():
    @dataclass(frozen=True)
    class WrappedModel:
        model: PetriNet

    upstream = parent(WrappedModel(sequence()))
    result = maximal_decompose_model(upstream)
    assert result.status is ComputeStatus.COMPUTED
    assert result.parent_computation_ids == (upstream.computation_id,)
    assert result.source_digest == upstream.source_digest
    assert recompose_maximal_decomposition(result).value == sequence()


def test_recomposition_refuses_a_coarser_partition_even_if_union_digest_matches():
    from pix.case_centric.maximal_decomposition import DecompositionComponent

    model = sequence()
    value = maximal_decompose_model(model).value
    component = DecompositionComponent("component-1", model, ("a", "b"), ())
    altered = replace(value, components=(component,))
    result = recompose_maximal_decomposition(altered)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert "finest partition" in result.issues[-1].message


def test_partial_coverage_is_not_an_incomplete_structure_certificate():
    result = maximal_decompose_model(parent(sequence(), ComputeStatus.PARTIAL))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.certificate.identical_structure
    assert result.value.certificate.identical_markings


@pytest.mark.parametrize("field", ["components", "certificate"])
def test_mutable_malformed_payload_returns_invalid_without_identity_exception(field):
    value = maximal_decompose_model(sequence()).value
    altered = replace(value, **{field: [] if field == "components" else {}})
    result = recompose_maximal_decomposition(altered)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.spec.decomposition is None
    assert result.issues[-1].code == "invalid_decomposition_payload"


@pytest.mark.parametrize("factory", [sequence, concurrent, duplicate_choice])
def test_public_codec_preserves_decomposition_and_recomposition(factory):
    from pix.results import result_from_json, result_json_bytes

    decomposition = maximal_decompose_model(factory())
    for result in (decomposition, recompose_maximal_decomposition(decomposition)):
        validate_maximal_decomposition_result(result)
        assert result_from_json(result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "change",
    ["source_digest", "false_certificate", "marking", "ownership", "reference_claim"],
)
def test_public_codec_rejects_contradictory_decomposition_witness(change):
    from pix.results import result_json_bytes

    result = maximal_decompose_model(sequence())
    value = result.value
    if change == "source_digest":
        value = replace(value, source_model_digest="unrelated-model")
    elif change == "false_certificate":
        value = replace(
            value, certificate=replace(value.certificate, identical_structure=False)
        )
    elif change == "marking":
        value = replace(
            value,
            certificate=replace(value.certificate, source_final_marking=Marking()),
        )
    elif change == "ownership":
        value = replace(value, place_ownership=())
    else:
        value = replace(value, reference_equivalence="verified")
    altered = replace(result, value=value)
    with pytest.raises(ValueError):
        validate_maximal_decomposition_result(altered)
    with pytest.raises(ValueError):
        result_json_bytes(altered)


@pytest.mark.parametrize("change", ["source_digest", "false_certificate"])
def test_reader_rejects_semantic_tampering_even_with_recomputed_document_digest(change):
    from pix.results import _digest, _json_bytes, result_document, result_from_json

    document = result_document(maximal_decompose_model(sequence()))
    value = document["computation"]["value"]
    if change == "source_digest":
        value["source_model_digest"] = "unrelated-model"
    else:
        value["certificate"]["identical_structure"] = False
    body = {key: value for key, value in document.items() if key != "document_digest"}
    document["document_digest"] = _digest(body)
    with pytest.raises(ValueError):
        result_from_json(_json_bytes(document))


def test_codec_rejects_recomposition_of_a_different_net():
    from pix.results import result_json_bytes

    result = recompose_maximal_decomposition(maximal_decompose_model(sequence()))
    with pytest.raises(ValueError, match="payload disagrees"):
        result_json_bytes(replace(result, value=choice()))


def test_failed_recomposition_can_persist_its_rejected_witness():
    from pix.results import result_from_json, result_json_bytes

    value = maximal_decompose_model(sequence()).value
    result = recompose_maximal_decomposition(replace(value, place_ownership=()))
    assert result.status is ComputeStatus.INVALID_INPUT
    validate_maximal_decomposition_result(result)
    assert result_from_json(result_json_bytes(result)) == result


def test_codec_validator_checks_requested_budget_against_complete_witness():
    result = maximal_decompose_model(sequence())
    altered = replace(
        result,
        spec=replace(result.spec, parameters=MaximalDecompositionSpec(max_nodes=1)),
    )
    with pytest.raises(ValueError, match="size bounds"):
        validate_maximal_decomposition_result(altered)


def test_partial_parent_keeps_valid_complete_certificate_in_public_codec():
    from pix.results import result_from_json, result_json_bytes

    result = maximal_decompose_model(parent(sequence(), ComputeStatus.PARTIAL))
    assert result_from_json(result_json_bytes(result)) == result
    rebuilt = recompose_maximal_decomposition(result)
    assert result_from_json(result_json_bytes(rebuilt)) == rebuilt
