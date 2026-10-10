"""Count-based selection: independently specified frequencies and boundaries."""

from dataclasses import replace

import pytest

from pix.case_centric import catalog_trace_variants, compare_trace_groups
from pix.case_centric.trace_catalog import TraceCatalogSpec, top_variant_count
from pix.case_centric.trace_comparison import TraceComparisonSpec, TraceGroup
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import read_result, write_result
from pix.viewer import build_visualization
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization


def case(cid, word, label="normal"):
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
        tuple(
            case(f"v{i}/{j:02}", ("A", str(i), "A"))
            for i, n in enumerate((60, 20, 10, 5, 5))
            for j in range(n)
        )
    )


@pytest.mark.parametrize(
    "percent,count,cases", [(0, 0, 0), (20, 1, 60), (80, 4, 95), (100, 5, 100)]
)
def test_variant_count_is_not_case_coverage(percent, count, cases):
    result = catalog_trace_variants(
        sample(), spec=TraceCatalogSpec(top_variant_percent=percent)
    )
    assert result.status is ComputeStatus.COMPUTED
    g = result.value.groups[0]
    assert len(g.selected_variant_ids) == count
    assert (
        sum(
            v.frequency for v in result.value.variants if v.id in g.selected_variant_ids
        )
        == cases
    )
    assert [v.frequency for v in result.value.variants] == [60, 20, 10, 5, 5]
    assert [v.cumulative_case_count for v in result.value.variants] == [
        60,
        80,
        90,
        95,
        100,
    ]


@pytest.mark.parametrize("n,p,k", [(7, 20, 2), (1, 1, 1), (0, 100, 0), (100, 20, 20)])
def test_integer_rounding(n, p, k):
    assert top_variant_count(n, p) == k


@pytest.mark.parametrize("p", [-1, 101, 20.5, True, "20", None])
def test_invalid_percent(p):
    with pytest.raises(ValueError):
        TraceCatalogSpec(top_variant_percent=p)


def test_groups_empty_traces_and_unassigned():
    log = CaseLog(
        (case("a", ()), case("b", ("A", "B"), "other"), case("c", ("A",), None))
    )
    value = catalog_trace_variants(log, group_attribute="quality").value
    assert value.unassigned_case_ids == ("c",)
    assert [len(g.case_ids) for g in value.groups] == [1, 1]
    assert value.variants[0].activities == ()
    assert value.variants[0].event_ids == ()
    empty = catalog_trace_variants(log, (TraceGroup("empty", ()),)).value
    assert empty.groups[0].variant_ids == () and len(empty.unassigned_case_ids) == 3
    assert catalog_trace_variants(CaseLog(())).value.source_case_count == 0
    assert catalog_trace_variants(log, group_attribute="missing").value.groups == ()


def test_shared_comparison_grouping_and_actual_event_identity():
    log = sample()
    groups = (
        TraceGroup("normal", tuple(t.id for t in log.traces)),
        TraceGroup("empty", ()),
    )
    catalog = catalog_trace_variants(log, groups).value
    comparison = compare_trace_groups(
        log, groups, spec=TraceComparisonSpec(candidates_per_group=5)
    ).value
    assert [(v.activities, v.case_ids) for v in catalog.variants] == [
        (v.activities, v.member_case_ids) for v in comparison.candidates
    ]
    first = catalog.variants[0]
    assert first.example_case_id == "v0/00" and first.event_ids == (
        "v0/00/0",
        "v0/00/1",
        "v0/00/2",
    )


@pytest.mark.parametrize(
    "spec,code",
    [
        (TraceCatalogSpec(max_variants=4), "variant_limit"),
        (TraceCatalogSpec(max_events=2), "event_limit"),
    ],
)
def test_limits_refuse_a_biased_prefix(spec, code):
    result = catalog_trace_variants(sample(), spec=spec)
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert code in {i.code for i in result.issues}


@pytest.mark.parametrize(
    "groups",
    [
        (TraceGroup("x", ("missing",)),),
        (TraceGroup("x", ("a",)), TraceGroup("y", ("a",))),
        (TraceGroup("x", ("a",), "a"),),
    ],
)
def test_invalid_group_selection(groups):
    with pytest.raises(ValueError):
        catalog_trace_variants(CaseLog((case("a", ("A",)),)), groups)


def test_incomplete_classifier_is_not_an_empty_sequence():
    log = CaseLog((CaseTrace("a", (CaseEvent("e", ()),)),))
    result = catalog_trace_variants(log)
    assert result.status is not ComputeStatus.COMPUTED and result.value is None


def test_native_and_view_codec_and_profile_identity(tmp_path):
    result = catalog_trace_variants(sample())
    assert read_result(write_result(result, tmp_path / "result.json")) == result
    view = build_visualization(result)
    assert loads_visualization(dumps_visualization(view)) == view
    changed = build_visualization(
        catalog_trace_variants(sample(), spec=TraceCatalogSpec(top_variant_percent=80))
    )
    assert view.panels[0].catalog_id != changed.panels[0].catalog_id


@pytest.mark.parametrize("change", ["count", "members", "rank", "prefix", "duplicate"])
def test_corrupt_payload_is_rejected(change):
    value = catalog_trace_variants(sample()).value
    v = value.variants[0]
    with pytest.raises(ValueError):
        if change == "prefix":
            replace(value, groups=(replace(value.groups[0], selected_variant_ids=()),))
        elif change == "duplicate":
            replace(value, variants=value.variants + (v,))
        else:
            fields = {
                "count": {"cumulative_case_count": 1},
                "members": {"case_ids": ("foreign",)},
                "rank": {"rank": 4},
            }[change]
            replace(value, variants=(replace(v, **fields), *value.variants[1:]))
