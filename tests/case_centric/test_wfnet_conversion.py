"""Independent accepted-language checks for the structural WF-net converter."""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
from itertools import product

import pytest

from pix.case_centric.wfnet_conversion import (
    WfNetConversionRequest,
    WfNetConversionSpec,
    wfnet_to_process_tree,
)
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def leaf(label):
    return ProcessTree("tau") if label is None else ProcessTree("activity", label)


def node(op, *children):
    return ProcessTree(op, children=children)


def net(places, transitions, arcs, source="s", sink="f"):
    return PetriNet(
        tuple(Place(p) for p in places),
        tuple(Transition(*t) for t in transitions),
        tuple(Arc(*a) for a in arcs),
        Marking(((source, 1),)),
        Marking(((sink, 1),)),
    )


def independent_net_language(model, max_length=5):
    """Own multiset firing, with no production semantics/alignment imports."""
    places = tuple(p.id for p in model.places)
    index = {p: i for i, p in enumerate(places)}
    initial = tuple(dict(model.initial_marking.tokens).get(p, 0) for p in places)
    final = tuple(dict(model.final_marking.tokens).get(p, 0) for p in places)
    actions = []
    for transition in model.transitions:
        before, after = Counter(), Counter()
        for arc in model.arcs:
            if arc.target == transition.id:
                before[index[arc.source]] += arc.weight
            if arc.source == transition.id:
                after[index[arc.target]] += arc.weight
        actions.append((transition.activity, before, after))
    seen, pending, accepted = {(initial, ())}, deque(((initial, ()),)), set()
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.add(word)
        for label, before, after in actions:
            if not all(marking[i] >= count for i, count in before.items()):
                continue
            next_word = word if label is None else word + (label,)
            if len(next_word) > max_length:
                continue
            next_marking = tuple(
                v - before[i] + after[i] for i, v in enumerate(marking)
            )
            state = (next_marking, next_word)
            if state not in seen:
                seen.add(state)
                pending.append(state)
        assert len(seen) < 200_000, (
            "independent test fixture exceeded finite enumeration budget"
        )
    return accepted


@lru_cache(maxsize=None)
def shuffled(left, right):
    if not left:
        return frozenset((right,))
    if not right:
        return frozenset((left,))
    return frozenset(
        {(left[0],) + suffix for suffix in shuffled(left[1:], right)}
        | {(right[0],) + suffix for suffix in shuffled(left, right[1:])}
    )


def independent_tree_language(tree, bound=5):
    def concat(left, right):
        return {a + b for a in left for b in right if len(a) + len(b) <= bound}

    if tree.operator == "activity":
        return {(tree.activity,)} if bound else set()
    if tree.operator == "tau":
        return {()}
    children = [independent_tree_language(child, bound) for child in tree.children]
    if tree.operator == "xor":
        return set.union(*children)
    if tree.operator == "loop":
        body, redo = children
        known = set(body)
        while True:
            extended = known | concat(concat(known, redo), body)
            if extended == known:
                return known
            known = extended
    words = {()}
    for child in children:
        if tree.operator == "sequence":
            words = concat(words, child)
        else:
            words = {
                word
                for a in words
                for b in child
                if len(a) + len(b) <= bound
                for word in shuffled(a, b)
            }
    return words


def sequence_net(labels=("A", "B", "C")):
    boundaries = ("s", *(f"p{i}" for i in range(len(labels) - 1)), "f")
    return net(
        boundaries,
        tuple((f"t{i}", label) for i, label in enumerate(labels)),
        tuple(
            edge
            for i in range(len(labels))
            for edge in ((boundaries[i], f"t{i}"), (f"t{i}", boundaries[i + 1]))
        ),
    )


def xor_net(labels=("A", "B", None)):
    return net(
        ("s", "f"),
        tuple((f"t{i}", a) for i, a in enumerate(labels)),
        tuple(
            edge
            for i in range(len(labels))
            for edge in (("s", f"t{i}"), (f"t{i}", "f"))
        ),
    )


def parallel_net(labels=("A", "B"), split_label=None, join_label=None):
    return net(
        ("s", "p", "q", "r", "u", "f"),
        (
            ("split", split_label),
            ("a", labels[0]),
            ("b", labels[1]),
            ("join", join_label),
        ),
        (
            ("s", "split"),
            ("split", "p"),
            ("split", "q"),
            ("p", "a"),
            ("a", "r"),
            ("q", "b"),
            ("b", "u"),
            ("r", "join"),
            ("u", "join"),
            ("join", "f"),
        ),
    )


def loop_net(body="A", redo="B"):
    return net(
        ("s", "entry", "exit", "f"),
        (("enter", None), ("body", body), ("redo", redo), ("leave", None)),
        (
            ("s", "enter"),
            ("enter", "entry"),
            ("entry", "body"),
            ("body", "exit"),
            ("exit", "redo"),
            ("redo", "entry"),
            ("exit", "leave"),
            ("leave", "f"),
        ),
    )


def converted(model, spec=WfNetConversionSpec()):
    result = wfnet_to_process_tree(model, spec)
    assert result.status is ComputeStatus.COMPUTED, result.issues
    assert result.value.complete
    assert result.value.certificate.comparison.equivalent is True
    assert result.value.certificate.comparison.complete
    assert result.value.certificate.comparison.left_reachability_complete
    assert result.value.certificate.comparison.right_reachability_complete
    assert result.value.model is not None
    return result


@pytest.mark.parametrize(
    "model,rule",
    [
        (sequence_net(), "sequence"),
        (xor_net(), "xor"),
        (parallel_net(), "parallel"),
        (loop_net(), "loop"),
    ],
)
def test_manual_operator_fixtures_have_actual_reduction_and_independent_language(
    model, rule
):
    result = converted(model).value
    assert rule in {step.rule for step in result.reductions}
    assert independent_net_language(model) == independent_tree_language(result.model)
    assert result.reductions[-1].original_transition_ids == tuple(
        t.id for t in model.transitions
    )


def test_sequence_rejects_permutations_and_preserves_repeated_occurrences():
    result = converted(sequence_net(("A", "A", "B"))).value
    assert independent_tree_language(result.model) == {("A", "A", "B")}


def test_parallel_is_shuffle_not_choice_or_serial_ab_ba_shortcut():
    model = parallel_net(split_label="Start", join_label="Finish")
    result = converted(model).value
    assert independent_tree_language(result.model) == {
        ("Start", "A", "B", "Finish"),
        ("Start", "B", "A", "Finish"),
    }


@pytest.mark.parametrize(
    "labels", [("A", "A"), ("a'\\\"()漢字", "A"), (None, "A"), (None, None)]
)
def test_parallel_retains_duplicate_arbitrary_and_silent_labels(labels):
    model = parallel_net(labels)
    result = converted(model).value
    assert independent_tree_language(result.model) == independent_net_language(model)
    if labels == ("A", "A"):
        assert independent_tree_language(result.model) == {("A", "A")}


@pytest.mark.parametrize(
    "body,redo", [("A", "B"), ("A", None), (None, "B"), (None, None), ("A", "A")]
)
def test_loop_certificate_covers_infinite_language_with_finite_markings(body, redo):
    model = loop_net(body, redo)
    result = converted(model).value
    assert independent_net_language(model, 7) == independent_tree_language(
        result.model, 7
    )
    if body == "A" and redo == "B":
        assert independent_tree_language(result.model, 5) == {
            ("A",),
            ("A", "B", "A"),
            ("A", "B", "A", "B", "A"),
        }


@pytest.mark.parametrize("labels", [("A", "A", None), (None,), ("a'\"雪",)])
def test_duplicate_choice_leaves_and_single_leaf_are_not_label_expressions(labels):
    model = xor_net(labels)
    result = converted(model).value
    assert independent_tree_language(result.model) == independent_net_language(model)
    if len(labels) > 1:
        assert len(result.model.children) == len(labels)


@pytest.mark.parametrize(
    "outer,inner,side",
    [
        (a, b, side)
        for a, b in product(("sequence", "xor", "parallel", "loop"), repeat=2)
        for side in (0, 1)
    ],
)
def test_nested_native_roundtrip_uses_independent_operator_semantics(
    outer, inner, side
):
    nested = node(inner, leaf("A"), leaf("B"))
    children = (nested, leaf("C")) if side == 0 else (leaf("C"), nested)
    original = node(outer, *children)
    original_net = process_tree_to_petri_net(original)
    result = converted(original_net).value
    assert independent_tree_language(result.model, 4) == independent_tree_language(
        original, 4
    )
    assert independent_net_language(original_net, 4) == independent_tree_language(
        original, 4
    )


def test_non_free_choice_residual_is_explicitly_unsupported_not_fallback_tree():
    base = parallel_net()
    mixed = replace(
        base,
        transitions=base.transitions + (Transition("mixed", "C"),),
        arcs=base.arcs
        + (Arc("p", "mixed"), Arc("q", "mixed"), Arc("mixed", "r"), Arc("mixed", "u")),
    )
    assert independent_net_language(mixed) == {("A", "B"), ("B", "A"), ("C",)}
    result = wfnet_to_process_tree(mixed)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "wfnet_irreducible" in {issue.code for issue in result.issues}


def test_weighted_arcs_are_refused_without_unit_arc_coercion():
    base = sequence_net(("A",))
    weighted = replace(base, arcs=tuple(replace(a, weight=2) for a in base.arcs))
    result = wfnet_to_process_tree(weighted)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "weighted_wfnet_unsupported" in {i.code for i in result.issues}
    assert independent_net_language(weighted) == set()


@pytest.mark.parametrize(
    "change",
    (
        "isolated_place",
        "isolated_transition",
        "two_initial_tokens",
        "wrong_final",
        "no_final",
    ),
)
def test_non_workflow_boundaries_are_not_reinterpreted(change):
    base = sequence_net()
    if change == "isolated_place":
        base = replace(base, places=base.places + (Place("isolated"),))
    elif change == "isolated_transition":
        base = replace(
            base, transitions=base.transitions + (Transition("isolated", "Z"),)
        )
    elif change == "two_initial_tokens":
        base = replace(base, initial_marking=Marking((("s", 2),)))
    elif change == "wrong_final":
        base = replace(base, final_marking=Marking((("p0", 1),)))
    else:
        base = replace(base, final_marking=Marking())
    result = wfnet_to_process_tree(base)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "workflow_structure_unsupported" in {i.code for i in result.issues}


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_reductions", 1),
        ("max_pattern_checks", 1),
        ("max_states", 1),
        ("max_comparison_states", 1),
    ],
)
def test_exhaustion_withholds_tree_and_never_claims_non_equivalence(field, value):
    result = wfnet_to_process_tree(
        sequence_net(), WfNetConversionSpec(**{field: value})
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.model is None
    assert not result.value.complete
    if result.value.certificate is not None:
        assert result.value.certificate.comparison.equivalent is None
        assert not result.value.certificate.comparison.complete


def test_token_cap_is_unknown_on_parallel_net():
    result = wfnet_to_process_tree(parallel_net(), WfNetConversionSpec(max_tokens=1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.certificate.comparison.equivalent is None
    assert result.value.model is None


def test_depth_cap_is_unknown_and_no_overdeep_candidate_is_released():
    original = node("xor", node("parallel", leaf("A"), leaf("B")), leaf("C"))
    result = wfnet_to_process_tree(
        process_tree_to_petri_net(original), WfNetConversionSpec(max_tree_depth=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.model is None


def test_exact_reduction_budget_is_inclusive():
    original = sequence_net()
    normal = converted(original)
    exact = converted(
        original, WfNetConversionSpec(max_reductions=len(normal.value.reductions))
    )
    assert normal.value.model == exact.value.model


def parent_result(model, status=ComputeStatus.COMPUTED):
    return ComputationResult(
        operator_id="test.source",
        operator_version="1.0.0",
        source_digest="log:digest",
        spec=WfNetConversionSpec(),
        status=status,
        value=model
        if status in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL)
        else None,
        issues=(ComputeIssue("parent_issue", "Retained evidence"),),
        computation_id="parent:id",
    )


def test_raw_and_derived_input_preserve_model_identity_and_parent_evidence():
    model = sequence_net()
    raw = converted(model)
    parent = parent_result(model)
    result = converted(parent)
    assert result.source_digest == "log:digest"
    assert raw.source_digest == result.value.source_model_digest
    assert result.spec.model_digest == raw.spec.model_digest
    assert result.value == raw.value
    assert result.parent_computation_ids[0] == parent.computation_id
    assert (
        result.parent_computation_ids[-1]
        == result.value.certificate.comparison_computation_id
    )
    assert parent.issues[0] in result.issues
    changed = converted(parent_result(sequence_net(("X", "B", "C"))))
    assert result.computation_id != changed.computation_id


def test_result_model_wrapper_is_accepted_without_changing_source():
    # Use an immutable local wrapper to model discovery/conversion payloads.
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Wrapper:
        model: PetriNet

    result = converted(parent_result(Wrapper(sequence_net())))
    assert result.source_digest == "log:digest"
    assert independent_tree_language(result.value.model) == {("A", "B", "C")}


@pytest.mark.parametrize(
    "status",
    (ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE, ComputeStatus.INVALID_INPUT),
)
def test_noncomputed_parent_is_not_promoted(status):
    result = wfnet_to_process_tree(parent_result(sequence_net(), status))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.parent_computation_ids == ("parent:id",)


def test_invalid_input_types_are_explicit():
    with pytest.raises(TypeError):
        wfnet_to_process_tree("net")
    with pytest.raises(TypeError):
        wfnet_to_process_tree(sequence_net(), None)
    result = wfnet_to_process_tree(parent_result(leaf("A")))
    assert result.status is ComputeStatus.INVALID_INPUT


@pytest.mark.parametrize(
    "field",
    (
        "max_reductions",
        "max_states",
        "max_tokens",
        "max_comparison_states",
        "max_tree_depth",
        "max_pattern_checks",
    ),
)
@pytest.mark.parametrize("invalid", (0, -1, True, 1.5, "10"))
def test_limits_are_strict_positive_integers(field, invalid):
    with pytest.raises(ValueError):
        WfNetConversionSpec(**{field: invalid})


def test_tree_depth_cannot_exceed_native_conversion_contract():
    with pytest.raises(ValueError):
        WfNetConversionSpec(max_tree_depth=129)


def test_result_is_immutable_and_repeatable():
    one = converted(sequence_net())
    two = converted(sequence_net())
    assert one.value == two.value
    assert one.computation_id == two.computation_id
    assert isinstance(one.spec, WfNetConversionRequest)
    with pytest.raises(FrozenInstanceError):
        one.value.complete = False


def test_user_ids_cannot_collide_with_generated_reduction_id():
    model = sequence_net()
    labels = {"t2": "pix:wfnet:reduction:0", "p1": "pix:wfnet:reduction:0:new"}
    renamed = replace(
        model,
        places=tuple(Place(labels.get(p.id, p.id)) for p in model.places),
        transitions=tuple(
            Transition(labels.get(t.id, t.id), t.activity) for t in model.transitions
        ),
        arcs=tuple(
            Arc(labels.get(a.source, a.source), labels.get(a.target, a.target))
            for a in model.arcs
        ),
    )
    result = converted(renamed)
    assert independent_tree_language(result.value.model) == {("A", "B", "C")}


@pytest.mark.parametrize("kind", ("computed", "partial", "unavailable"))
def test_persisted_result_roundtrip_keeps_certificate_bounds_and_absence(kind):
    from pix.results import result_from_json, result_json_bytes

    if kind == "computed":
        result = converted(loop_net())
    elif kind == "partial":
        result = wfnet_to_process_tree(
            parallel_net(), WfNetConversionSpec(max_tokens=1)
        )
    else:
        original = sequence_net(("A",))
        result = wfnet_to_process_tree(
            replace(original, arcs=tuple(replace(a, weight=2) for a in original.arcs))
        )
    decoded = result_from_json(result_json_bytes(result))
    assert decoded == result


def test_certificate_rejects_a_behavior_changing_candidate_with_actual_counterexample(
    monkeypatch,
):
    from pix.case_centric import wfnet_conversion

    # Exercise the gate independently from candidate construction: a broken
    # downstream tree compiler must not release an unverified conversion.
    monkeypatch.setattr(
        wfnet_conversion,
        "process_tree_to_petri_net",
        lambda _: sequence_net(("wrong",)),
    )
    result = wfnet_to_process_tree(sequence_net(("A",)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    issue = next(
        i for i in result.issues if i.code == "wfnet_certificate_counterexample"
    )
    assert issue.at in (("A",), ("wrong",))
    assert result.parent_computation_ids
