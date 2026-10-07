"""Independent visible-language and marking checks for both DFG constructions.

The language oracle tests words against only adjacency and observed boundary
sets. The Petri-net oracle performs its own incidence arithmetic and never
uses PIX enabled/fire/replay/alignment or conversion witness identifiers.
"""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from pix.case_centric.dfg_conversion import (
    RESULT_SCHEMAS,
    DFGConversionRequest,
    DFGConversionSpec,
    dfg_to_petri_net,
)
from pix.case_centric.discovery import (
    CaseRelationGraph,
    RelationDiscoverySpec,
    RelationEdge,
    discover_dfg,
)
from pix.contracts.analysis import (
    ActivityCount,
    BoundaryCount,
    BoundaryEvidence,
    DirectlyFollowsEdge,
    DirectlyFollowsGraph,
    TransitionEvidence,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace

VARIANTS = ("activity_defines_place", "invisibles_no_duplicates")


def log_of(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}:{j}", (CaseAttribute("concept:name", "string", a),)
                    )
                    for j, a in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def graph_of(*words):
    """Construct from words without invoking PIX discovery."""
    activities, starts, ends, counts, case_counts = (Counter() for _ in range(5))
    for word in words:
        activities.update(word)
        if word:
            starts[word[0]] += 1
            ends[word[-1]] += 1
        pairs = list(zip(word, word[1:]))
        counts.update(pairs)
        case_counts.update(set(pairs))
    return CaseRelationGraph(
        "directly_follows",
        tuple(sorted(activities.items())),
        tuple(
            RelationEdge(a, b, n, case_counts[a, b])
            for (a, b), n in sorted(counts.items())
        ),
        tuple(sorted(starts.items())),
        tuple(sorted(ends.items())),
        len(words),
        sum(not w for w in words),
        sum(counts.values()),
        True,
    )


def converted(graph, variant="invisibles_no_duplicates", **kwargs):
    result = dfg_to_petri_net(graph, DFGConversionSpec(variant, **kwargs))
    assert result.status is ComputeStatus.COMPUTED, result.issues
    assert result.value is not None
    return result


def word_oracle(graph, limit=5):
    activities = tuple(a for a, _ in graph.activity_counts)
    starts, ends = dict(graph.start_counts), dict(graph.end_counts)
    edges = {(e.source, e.target) for e in graph.edges}
    return ({()} if graph.empty_trace_count else set()) | {
        word
        for size in range(1, limit + 1)
        for word in product(activities, repeat=size)
        if word[0] in starts
        and word[-1] in ends
        and all(pair in edges for pair in zip(word, word[1:]))
    }


def pt_oracle(model, limit=5):
    incidences = []
    for transition in model.transitions:
        consumed, produced = Counter(), Counter()
        for arc in model.arcs:
            if arc.target == transition.id:
                consumed[arc.source] += arc.weight
            if arc.source == transition.id:
                produced[arc.target] += arc.weight
        incidences.append((transition.activity, consumed, produced))
    initial = (model.initial_marking.tokens, ())
    pending, seen, accepted = deque([initial]), {initial}, set()
    while pending:
        marking, word = pending.popleft()
        # The safety check is independent of the converter's node names.
        assert sum(n for _, n in marking) == 1
        if marking == model.final_marking.tokens:
            accepted.add(word)
        tokens = Counter(dict(marking))
        for activity, consumed, produced in incidences:
            if activity is not None and len(word) == limit:
                continue
            if any(tokens[p] < n for p, n in consumed.items()):
                continue
            after = tokens.copy()
            after.subtract(consumed)
            after.update(produced)
            state = (
                tuple(sorted((p, n) for p, n in after.items() if n)),
                word if activity is None else (*word, activity),
            )
            if state not in seen:
                seen.add(state)
                assert len(seen) < 100_000, "independent oracle bound reached"
                pending.append(state)
    return accepted


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize(
    "words",
    [
        ("ABC",),
        ("A",),
        ("",),
        ("", ""),
        ("A", ""),
        ("AB", "BA"),
        ("AABA", "AC", ""),
        ("ABX", "CBY"),
        ("A", "B", "AB", "BA"),
        (("▶", "■", "dfg:p:start", "한글"), ("dfg:p:start",)),
    ],
)
def test_hand_specified_graph_languages_and_single_token_invariant(variant, words):
    graph = graph_of(*words)
    actual = converted(graph, variant)
    assert pt_oracle(actual.value.model, 4) == word_oracle(graph, 4)
    assert actual.value.allows_empty_trace == any(not word for word in words)
    assert actual.value.input_kind == "case_relation_graph"
    assert actual.value.projected_object_type is None


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("mask", range(16))
def test_every_binary_direct_relation_with_all_nonempty_boundary_sets(variant, mask):
    """16 graphs x 9 boundary pairs x both epsilon policies for each variant."""
    pairs = tuple(product("AB", repeat=2))
    edge_pairs = tuple(pair for index, pair in enumerate(pairs) if mask & (1 << index))
    for starts, ends, empty in product(("A", "B", "AB"), ("A", "B", "AB"), (0, 1)):
        nonempty = len(starts) * len(ends)
        graph = CaseRelationGraph(
            "directly_follows",
            (("A", 100), ("B", 100)),
            tuple(RelationEdge(a, b, 1, 1) for a, b in edge_pairs),
            tuple((a, len(ends)) for a in starts),
            tuple((a, len(starts)) for a in ends),
            nonempty + empty,
            empty,
            len(edge_pairs),
            True,
        )
        assert pt_oracle(converted(graph, variant).value.model, 4) == word_oracle(
            graph, 4
        )


def test_profiles_are_structurally_distinct_with_identical_walk_languages():
    graph = graph_of("AB", "CB", "B")
    place = converted(graph, VARIANTS[0])
    unique = converted(graph, VARIANTS[1])
    assert place.value.model != unique.value.model
    assert place.computation_id != unique.computation_id
    assert place.value.profile != unique.value.profile
    assert sum(t.activity == "B" for t in place.value.model.transitions) == 3
    assert sum(t.activity == "B" for t in unique.value.model.transitions) == 1
    assert all(len(ids) == 1 for _, ids in place.value.activity_places)
    assert all(len(ids) == 2 for _, ids in unique.value.activity_places)
    assert (
        pt_oracle(place.value.model)
        == pt_oracle(unique.value.model)
        == word_oracle(graph)
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_dfg_recombination_is_not_original_trace_language(variant):
    graph = graph_of("ABX", "CBY")
    actual = pt_oracle(converted(graph, variant).value.model, 3)
    assert actual == {tuple(w) for w in ("ABX", "ABY", "CBX", "CBY")}


@pytest.mark.parametrize("variant", VARIANTS)
def test_observed_boundaries_override_in_out_degree_even_inside_cycles(variant):
    graph = graph_of("ABABA")
    assert pt_oracle(converted(graph, variant).value.model, 5) == {
        ("A",),
        tuple("ABA"),
        tuple("ABABA"),
    }


@pytest.mark.parametrize("variant", VARIANTS)
def test_frequency_does_not_change_graph_language_or_arc_weights(variant):
    single = converted(graph_of("AB", "AC"), variant)
    weighted = converted(graph_of(*(["AB"] * 17), *(["AC"] * 3)), variant)
    assert single.value.model == weighted.value.model
    assert single.computation_id != weighted.computation_id
    assert all(a.weight == 1 for a in weighted.value.model.arcs)


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("counting", ("occurrences", "cases"))
def test_actual_miner_composition_preserves_parent_and_counting(variant, counting):
    source = discover_dfg(
        log_of("ABABA", "AC", ""), RelationDiscoverySpec(counting=counting)
    )
    output = converted(source, variant)
    assert output.source_digest == source.source_digest
    assert output.parent_computation_ids == (source.computation_id,)
    assert pt_oracle(output.value.model) == word_oracle(source.value)


def projection():
    return DirectlyFollowsGraph(
        "Order",
        2,
        ("empty-order",),
        (
            ActivityCount("A", 1, ("e1",), ("order",)),
            ActivityCount("B", 1, ("e2",), ("order",)),
        ),
        (
            DirectlyFollowsEdge(
                "A", "B", 1, (TransitionEvidence("order", "e1", "e2", (), ()),)
            ),
        ),
        (BoundaryCount("A", (BoundaryEvidence("order", "e1"),)),),
        (BoundaryCount("B", (BoundaryEvidence("order", "e2"),)),),
    )


@pytest.mark.parametrize("variant", VARIANTS)
def test_existing_explicit_object_type_projection_is_a_classical_net(variant):
    source = projection()
    output = converted(source, variant)
    assert output.value.input_kind == "object_type_projection"
    assert output.value.projected_object_type == "Order"
    assert pt_oracle(output.value.model) == {(), ("A", "B")}


@pytest.mark.parametrize("variant", VARIANTS)
def test_actual_ocel_dfg_with_shared_events_repeated_activity_and_empty_object(variant):
    from pix.compute.dfg import discover_dfg as discover_projection
    from pix.contracts.analysis import TraceSpec
    from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    log = OCEL(
        event_types=tuple(EventType(a) for a in "ABC"),
        object_types=(ObjectType("Order"),),
        events=tuple(
            Event(f"e{i}", a, origin + timedelta(seconds=i))
            for i, a in enumerate("ABACA")
        ),
        objects=tuple(Object(obj, "Order") for obj in ("one", "two", "solo", "empty")),
        e2o=tuple(
            E2O(f"e{i}", obj, "")
            for obj, indices in (("one", (0, 1, 2)), ("two", (1, 3)), ("solo", (4,)))
            for i in indices
        ),
    )
    source = discover_projection(log, TraceSpec("Order"))
    result = converted(source, variant)
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == (source.computation_id,)
    assert pt_oracle(result.value.model, 4) == word_oracle(
        graph_of("ABA", "BC", "A", ""), 4
    )


def parent_result(graph, status=ComputeStatus.COMPUTED):
    return ComputationResult(
        "test.dfg",
        "1.0.0",
        "same-source",
        RelationDiscoverySpec(),
        status,
        graph if status in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL) else None,
        (ComputeIssue("source_witness", "Preserve this evidence"),),
        "same-parent",
    )


def test_input_digest_prevents_collision_under_same_parent():
    one = converted(parent_result(graph_of("AB")))
    two = converted(parent_result(graph_of("AB", "")))
    assert one.source_digest == two.source_digest
    assert one.parent_computation_ids == two.parent_computation_ids
    assert one.computation_id != two.computation_id
    assert one.spec.model_digest == one.value.source_model_digest
    assert one.issues[0].code == "source_witness"


@pytest.mark.parametrize(
    "status",
    [ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE, ComputeStatus.INVALID_INPUT],
)
def test_noncomputed_parents_do_not_become_complete_nets(status):
    source = parent_result(graph_of("AB"), status)
    output = dfg_to_petri_net(source)
    assert output.status is ComputeStatus.UNAVAILABLE
    assert output.value is None
    assert output.parent_computation_ids == (source.computation_id,)
    assert source.issues[0] in output.issues


def test_complete_parent_with_wrong_payload_is_invalid():
    output = dfg_to_petri_net(parent_result("not-a-graph"))
    assert output.status is ComputeStatus.INVALID_INPUT
    assert output.value is None


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("field", ("max_net_nodes", "max_net_arcs"))
@pytest.mark.parametrize("words", (("AB", ""), ("",)))
def test_exact_resource_budget_and_one_below(variant, field, words):
    graph = graph_of(*words)
    model = converted(graph, variant).value.model
    size = (
        len(model.arcs)
        if field == "max_net_arcs"
        else len(model.places) + len(model.transitions)
    )
    assert converted(graph, variant, **{field: size}).value.model == model
    output = dfg_to_petri_net(graph, DFGConversionSpec(variant, **{field: size - 1}))
    assert output.status is ComputeStatus.UNAVAILABLE
    assert output.value is None
    assert output.issues[-1].code == "dfg_conversion_limit"


@pytest.mark.parametrize("variant", VARIANTS)
def test_empty_log_and_partial_edges_do_not_synthesize_epsilon(variant):
    for graph, code in (
        (graph_of(), "dfg_empty_log"),
        (replace(graph_of("AB"), complete=False), "dfg_incomplete"),
    ):
        output = dfg_to_petri_net(graph, DFGConversionSpec(variant))
        assert output.status is ComputeStatus.UNAVAILABLE
        assert output.value is None
        assert output.issues[-1].code == code


@pytest.mark.parametrize(
    "field,value",
    [
        ("variant", "unknown"),
        ("variant", None),
        ("max_net_nodes", 0),
        ("max_net_nodes", -1),
        ("max_net_nodes", True),
        ("max_net_nodes", 1.5),
        ("max_net_arcs", False),
        ("max_net_arcs", "3"),
    ],
)
def test_invalid_parameters(field, value):
    with pytest.raises((ValueError, TypeError)):
        DFGConversionSpec(**{field: value})


def malformed_graphs():
    graph = graph_of("AB")
    yield replace(graph, relation="eventually_follows")
    yield replace(graph, complete=1)
    yield replace(graph, trace_count=True)
    yield replace(graph, empty_trace_count=2)
    yield replace(graph, examined_event_pairs=-1)
    yield replace(graph, activity_counts=(("A", 0), ("B", 1)))
    yield replace(graph, activity_counts=(("A", 1), ("A", 1)))
    yield replace(graph, activity_counts=(("", 1), ("B", 1)))
    yield replace(graph, activity_counts=(("\ud800", 1), ("B", 1)))
    yield replace(graph, start_counts=())
    yield replace(graph, start_counts=(("Z", 1),))
    yield replace(graph, end_counts=(("B", 2),))
    yield replace(graph, edges=(RelationEdge("A", "Z", 1, 1),))
    yield replace(graph, edges=graph.edges * 2)
    yield replace(graph, edges=(RelationEdge("A", "B", 0, 0),))
    yield replace(graph, edges=(RelationEdge("A", "B", 1, 2),))
    yield replace(graph, edges=(RelationEdge("A", "B", True, 1),))
    yield replace(graph, edges=(RelationEdge("A", "B", 2, 1),))
    yield replace(graph, edges=("AB",))
    yield replace(graph, activity_counts=[("A", 1), ("B", 1)])
    yield replace(projection(), empty_object_ids=("empty-order", "empty-order"))
    yield replace(projection(), object_count=1)
    yield replace(projection(), starts=())
    yield replace(projection(), activities=())
    yield replace(projection(), edges=(DirectlyFollowsEdge("A", "Z", 1, ()),))
    yield replace(projection(), starts=(BoundaryCount("A", ("wrong-type",)),))
    yield replace(
        projection(),
        starts=(BoundaryCount("A", (BoundaryEvidence("wrong-object", "e1"),)),),
    )
    yield replace(
        projection(),
        ends=(BoundaryCount("B", (BoundaryEvidence("order", "wrong-event"),)),),
    )
    yield replace(projection(), empty_object_ids=("order",))
    yield replace(
        projection(),
        activities=(
            replace(projection().activities[0], object_ids=()),
            projection().activities[1],
        ),
    )
    yield replace(projection(), edges=(replace(projection().edges[0], evidence=()),))
    yield replace(
        projection(), edges=(replace(projection().edges[0], evidence=("wrong-type",)),)
    )
    yield replace(
        projection(),
        edges=(
            replace(
                projection().edges[0],
                evidence=(TransitionEvidence("order", "e1", "unknown", (), ()),),
            ),
        ),
    )
    yield replace(projection(), edges=())
    yield replace(
        projection(),
        activities=(
            replace(projection().activities[0], event_occurrence_count=2),
            projection().activities[1],
        ),
    )


@pytest.mark.parametrize("graph", tuple(malformed_graphs()))
def test_malformed_graph_is_rejected_without_a_model(graph):
    result = dfg_to_petri_net(graph)
    assert result.status is ComputeStatus.INVALID_INPUT, result.issues
    assert result.value is None


def test_raw_input_types_are_explicit():
    with pytest.raises(TypeError):
        dfg_to_petri_net({("A", "B"): 1})
    with pytest.raises(TypeError):
        dfg_to_petri_net(graph_of("AB"), {})


def test_projection_one_event_cannot_have_two_activity_labels():
    malformed = DirectlyFollowsGraph(
        "Order",
        1,
        (),
        tuple(ActivityCount(a, 1, ("event",), ("order",)) for a in "AB"),
        (
            DirectlyFollowsEdge(
                "A", "B", 1, (TransitionEvidence("order", "event", "event", (), ()),)
            ),
        ),
        (BoundaryCount("A", (BoundaryEvidence("order", "event"),)),),
        (BoundaryCount("B", (BoundaryEvidence("order", "event"),)),),
    )
    assert dfg_to_petri_net(malformed).status is ComputeStatus.INVALID_INPUT


def test_projection_disconnected_cycle_cannot_pass_as_a_complete_object_trace():
    malformed = DirectlyFollowsGraph(
        "Order",
        1,
        (),
        (
            ActivityCount("A", 2, ("a1", "a2"), ("order",)),
            ActivityCount("B", 2, ("b1", "b2"), ("order",)),
        ),
        (
            DirectlyFollowsEdge(
                "A", "A", 1, (TransitionEvidence("order", "a1", "a2", (), ()),)
            ),
            DirectlyFollowsEdge(
                "B",
                "B",
                2,
                (
                    TransitionEvidence("order", "b1", "b2", (), ()),
                    TransitionEvidence("order", "b2", "b1", (), ()),
                ),
            ),
        ),
        (BoundaryCount("A", (BoundaryEvidence("order", "a1"),)),),
        (BoundaryCount("A", (BoundaryEvidence("order", "a2"),)),),
    )
    assert dfg_to_petri_net(malformed).status is ComputeStatus.INVALID_INPUT


@pytest.mark.parametrize("variant", VARIANTS)
def test_registered_json_codec_roundtrip_for_computed_and_unavailable(variant):
    from pix.results import result_from_json, result_json_bytes

    spec = DFGConversionSpec(variant)
    for source in (
        graph_of("AB", ""),
        projection(),
        graph_of(),
        replace(graph_of("AB"), relation="eventually_follows"),
    ):
        result = dfg_to_petri_net(source, spec)
        assert result_from_json(result_json_bytes(result)) == result


def test_immutable_results_and_deterministic_graph_node_identifiers():
    graph = graph_of("AB", "CB")
    result = converted(graph)
    with pytest.raises(FrozenInstanceError):
        result.value.profile = "changed"
    with pytest.raises(FrozenInstanceError):
        result.value.model.places = ()
    reordered = replace(
        graph,
        activity_counts=tuple(reversed(graph.activity_counts)),
        edges=tuple(reversed(graph.edges)),
        start_counts=tuple(reversed(graph.start_counts)),
    )
    assert converted(reordered).value.model == result.value.model
    assert converted(graph) == result
    assert RESULT_SCHEMAS[result.operator_id][1] is DFGConversionRequest
