"""Group selection, independent edit oracle, identities and partial coverage."""

import json
from dataclasses import replace
from functools import lru_cache
from itertools import product

import pytest

from pix.case_centric import compare_trace_groups
from pix.case_centric.sequence_alignment import SequenceAlignmentSpec
from pix.case_centric.trace_comparison import TraceComparisonSpec, TraceGroup
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import read_result, write_result
from pix.viewer import build_visualization, render_html
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization


def case(cid, word, label=None):
    return CaseTrace(
        cid,
        tuple(
            CaseEvent(f"{cid}/{i}", (CaseAttribute("concept:name", "string", a),))
            for i, a in enumerate(word)
        ),
        () if label is None else (CaseAttribute("quality", "string", label),),
    )


def sample():
    return CaseLog(
        (
            case("n2", ("A", "B", "C"), "normal"),
            case("n1", ("A", "B", "C"), "normal"),
            case("n3", ("A", "C"), "normal"),
            case("b1", ("A", "X", "B", "C"), "abnormal"),
            case("b2", ("A", "X", "B", "C"), "abnormal"),
            case("b3", ("A", "B", "D"), "abnormal"),
            case("unknown", ("A",)),
        )
    )


def test_frequency_selection_retains_population_identity_and_unassigned_cases(tmp_path):
    log = sample()
    result = compare_trace_groups(
        log,
        group_attribute="quality",
        spec=TraceComparisonSpec(reference_group="normal"),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.unassigned_case_ids == ("unknown",)
    groups = {g.name: g for g in result.value.groups}
    candidates = {c.id: c for c in result.value.candidates}
    normal = candidates[groups["normal"].selected_candidate_id]
    abnormal = candidates[groups["abnormal"].selected_candidate_id]
    assert normal.case_id == "n1"
    assert normal.activities == ("A", "B", "C")
    assert normal.member_case_ids == ("n1", "n2")
    assert len(groups["normal"].case_ids) == 3
    pair = next(
        a
        for a in result.value.alignments
        if (a.candidate_id, a.reference_id) == (abnormal.id, normal.id)
    )
    assert pair.cost == 1
    assert [(m.kind, m.log_activity, m.model_activity) for m in pair.moves] == [
        ("synchronous", "A", "A"),
        ("log", "X", None),
        ("synchronous", "B", "B"),
        ("synchronous", "C", "C"),
    ]
    path = write_result(result, tmp_path / "comparison.json")
    assert read_result(path) == result
    # Group names and ordering are part of the request identity.
    other = compare_trace_groups(
        log, (TraceGroup("N", ("n1", "n2", "n3")), TraceGroup("B", ("b1", "b2", "b3")))
    )
    assert other.computation_id != result.computation_id
    assert other.source_digest == result.source_digest


def test_manual_case_is_selected_even_when_its_variant_is_outside_top_k():
    result = compare_trace_groups(
        sample(),
        (
            TraceGroup("normal", ("n1", "n2", "n3"), "n3"),
            TraceGroup("abnormal", ("b1", "b2", "b3")),
        ),
        spec=TraceComparisonSpec(candidates_per_group=1),
    )
    rep = result.value.candidates[0]
    assert (rep.case_id, rep.rank, rep.frequency, rep.selection) == (
        "n3",
        2,
        1,
        "manual",
    )
    assert result.value.groups[0].selected_candidate_id == rep.id
    assert len(result.value.groups[0].case_ids) == 3


@pytest.mark.parametrize("budget", ["pair", "total", "candidates"])
def test_limits_are_explicit_and_never_fabricate_zero_cost(budget):
    spec = {
        "pair": TraceComparisonSpec(alignment=SequenceAlignmentSpec(max_cells=1)),
        "total": TraceComparisonSpec(max_total_cells=1),
        "candidates": TraceComparisonSpec(max_candidates=1),
    }[budget]
    result = compare_trace_groups(sample(), group_attribute="quality", spec=spec)
    if budget == "candidates":
        assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    else:
        assert result.status is ComputeStatus.PARTIAL
        assert all(
            a.status == "cell_limit" and a.cost is None and not a.moves
            for a in result.value.alignments
        )
        assert len(result.value.groups) == 2


def test_empty_group_empty_sequence_and_all_empty_sequences_are_distinct():
    log = CaseLog((case("empty", ()), case("empty2", ()), case("activity", ("A",))))
    result = compare_trace_groups(
        log,
        (
            TraceGroup("empty trace", ("empty",)),
            TraceGroup("activity", ("activity",)),
            TraceGroup("no cases", ()),
        ),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.groups[-1].candidate_ids == ()
    assert result.value.candidates[0].activities == ()
    assert {a.cost for a in result.value.alignments} == {1}
    result = compare_trace_groups(
        log, (TraceGroup("one", ("empty",)), TraceGroup("two", ("empty2",)))
    )
    assert result.status is ComputeStatus.COMPUTED
    assert all(a.cost == 0 and a.moves == () for a in result.value.alignments)


@pytest.mark.parametrize(
    "groups",
    [
        (TraceGroup("a", ("n1",)),),
        (TraceGroup("a", ("n1",)), TraceGroup("a", ("n2",))),
        (TraceGroup("a", ("n1",)), TraceGroup("b", ("n1",))),
        (TraceGroup("a", ("absent",)), TraceGroup("b", ("n2",))),
    ],
)
def test_invalid_groups_refuse_ambiguous_memberships(groups):
    with pytest.raises(ValueError):
        compare_trace_groups(sample(), groups)


def test_ties_use_sequence_then_case_id_and_preserve_repeated_activities():
    log = CaseLog(
        (
            case("z", ("A", "A")),
            case("a", ("A", "A")),
            case("b", ("A", "B")),
            case("c", ("A", "B")),
            case("x", ("B",)),
        )
    )
    result = compare_trace_groups(
        log, (TraceGroup("N", ("z", "a", "b", "c")), TraceGroup("B", ("x",)))
    )
    assert result.value.candidates[0].case_id == "a"
    assert result.value.candidates[0].activities == ("A", "A")
    assert result.value.candidates[1].rank == 2


@pytest.mark.parametrize("costs", [(1, 1, 1), (2, 3, None), (0, 0, 0)])
def test_small_words_against_independent_recursive_distance(costs):
    @lru_cache(None)
    def distance(left, right):
        if not left:
            return len(right) * costs[1]
        if not right:
            return len(left) * costs[0]
        values = [
            costs[0] + distance(left[1:], right),
            costs[1] + distance(left, right[1:]),
        ]
        if left[0] == right[0]:
            values.append(distance(left[1:], right[1:]))
        elif costs[2] is not None:
            values.append(costs[2] + distance(left[1:], right[1:]))
        return min(values)

    words = [w for n in range(3) for w in product("AB", repeat=n)]
    log = CaseLog(tuple(case(str(i), word) for i, word in enumerate(words)))
    groups = tuple(TraceGroup(str(i), (str(i),)) for i in range(len(words)))
    result = compare_trace_groups(
        log, groups, spec=TraceComparisonSpec(alignment=SequenceAlignmentSpec(*costs))
    )
    reps = {c.id: c for c in result.value.candidates}
    for pair in result.value.alignments:
        left, right = reps[pair.candidate_id], reps[pair.reference_id]
        assert pair.cost == distance(left.activities, right.activities)
        assert (
            tuple(m.log_activity for m in pair.moves if m.log_activity is not None)
            == left.activities
        )
        assert (
            tuple(m.model_activity for m in pair.moves if m.model_activity is not None)
            == right.activities
        )


def test_visualization_is_one_comparison_panel_and_strict_roundtrip():
    result = compare_trace_groups(sample(), group_attribute="quality")
    doc = build_visualization(result)
    assert len(doc.panels) == 1 and doc.panels[0].kind == "trace_comparison"
    assert loads_visualization(dumps_visualization(doc)) == doc
    assert doc.provenance[0].calculation_id == result.computation_id
    html = render_html(doc)
    assert "renderTraceComparison" in html
    assert "Representative for" in html
    forged = json.loads(dumps_visualization(doc))
    forged["panels"][0]["alignments"][0]["cost"] += 1
    with pytest.raises(ValueError, match="cost differs"):
        loads_visualization(json.dumps(forged))
    forged = json.loads(dumps_visualization(doc))
    forged["panels"][0]["candidates"][0]["unexpected"] = True
    with pytest.raises(ValueError, match="fields differ"):
        loads_visualization(json.dumps(forged))


def test_hostile_labels_are_text_and_no_evidence_is_mutated():
    attack = '</script><img src=x onerror="alert(1)">'
    log = CaseLog((case("a", (attack,), attack), case("b", ("ok",), "normal")))
    result = compare_trace_groups(log, group_attribute="quality")
    doc = build_visualization(result)
    html = render_html(doc)
    assert attack not in html
    assert loads_visualization(dumps_visualization(doc)) == doc
    assert log.traces[0].events[0].attributes[0].value == attack


def test_forged_witness_and_missing_pair_are_rejected():
    value = compare_trace_groups(sample(), group_attribute="quality").value
    with pytest.raises(ValueError, match="every cross-group"):
        replace(value, alignments=value.alignments[:-1])
    first = value.alignments[0]
    with pytest.raises(ValueError, match="reconstruct"):
        replace(
            value,
            alignments=(replace(first, moves=first.moves[:-1]), *value.alignments[1:]),
        )


def test_missing_and_null_labels_are_unassigned_and_typed_collisions_are_refused():
    log = sample()
    null = CaseTrace("null", (), (CaseAttribute("quality", "null"),))
    result = compare_trace_groups(
        replace(log, traces=log.traces + (null,)), group_attribute="quality"
    )
    assert result.value.unassigned_case_ids == ("null", "unknown")
    collision = CaseLog(
        (
            CaseTrace("a", (), (CaseAttribute("quality", "int", 1),)),
            CaseTrace("b", (), (CaseAttribute("quality", "string", "1"),)),
        )
    )
    with pytest.raises(ValueError, match="ambiguous typed"):
        compare_trace_groups(collision, group_attribute="quality")


def test_boolean_groups_are_supported_and_source_order_is_not_timestamp_sorted():
    from datetime import datetime, timezone

    traces = []
    for cid, label in (("n", False), ("b", True)):
        events = tuple(
            CaseEvent(
                f"{cid}/{i}",
                (
                    CaseAttribute("concept:name", "string", activity),
                    CaseAttribute(
                        "time:timestamp",
                        "date",
                        datetime(2026, 1, day, tzinfo=timezone.utc),
                    ),
                ),
            )
            for i, (activity, day) in enumerate(
                (("Later first", 2), ("Earlier second", 1))
            )
        )
        traces.append(
            CaseTrace(cid, events, (CaseAttribute("quality", "boolean", label),))
        )
    result = compare_trace_groups(CaseLog(tuple(traces)), group_attribute="quality")
    assert [g.name for g in result.value.groups] == ["false", "true"]
    assert all(
        c.activities == ("Later first", "Earlier second")
        for c in result.value.candidates
    )


def test_partial_total_budget_preserves_computed_pairs_and_refuses_other_pairs():
    log = CaseLog((case("a", ("A",)), case("b", ("B",)), case("c", ("C",))))
    result = compare_trace_groups(
        log,
        tuple(TraceGroup(cid, (cid,)) for cid in "abc"),
        spec=TraceComparisonSpec(max_total_cells=4),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert sum(a.status == "optimal" for a in result.value.alignments) == 1
    assert sum(a.status == "cell_limit" for a in result.value.alignments) == 5
    assert next(a for a in result.value.alignments if a.status == "optimal").cost == 1
    assert (
        loads_visualization(dumps_visualization(build_visualization(result))).status
        == "partial"
    )


def test_group_comparison_rejects_implicit_ocel_input():

    # The concrete OC projection examples have their own tests. This gate keeps
    # the new entry point from implicitly accepting raw object-centric input.
    from pix.ocel import OCEL

    with pytest.raises(TypeError, match="CaseLog"):
        compare_trace_groups(OCEL(), (TraceGroup("a", ()), TraceGroup("b", ())))
