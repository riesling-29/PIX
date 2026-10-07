from pix.case_centric.dfg_relations import DFGRelationSpec, dfg_relations
from pix.case_centric.model_discovery import (
    ModelFootprintSpec,
    discover_model_footprints,
)
from pix.case_centric.powl import POWLNode
from pix.contracts.result import ComputeStatus
from pix.model_io import DFGFile
from pix.results import result_from_json, result_json_bytes


def test_alpha_and_heuristics_and_boundaries_have_hand_calculated_relations():
    graph = DFGFile(
        ("A", "B", "C", "D"),
        (("A", "B", 4), ("B", "A", 1), ("B", "C", 2), ("C", "C", 2)),
        (("A", 2),),
        (("C", 2),),
    )
    alpha = dfg_relations(graph)
    assert [(r.source, r.target) for r in alpha.value.causal] == [("B", "C")]
    assert alpha.value.parallel == (("A", "B"), ("B", "A"))
    assert alpha.value.self_succession == ("C",)
    assert ("A", "D") in alpha.value.unrelated
    heuristics = dfg_relations(graph, DFGRelationSpec("heuristics", 0.49))
    ab = next(r for r in heuristics.value.causal if (r.source, r.target) == ("A", "B"))
    assert ab.score == 0.5
    strict = dfg_relations(graph, DFGRelationSpec("heuristics", 0.5))
    assert not any((r.source, r.target) == ("A", "B") for r in strict.value.causal)
    assert result_from_json(result_json_bytes(heuristics)) == heuristics
    assert (
        dfg_relations(graph, DFGRelationSpec(max_activity_pairs=1)).status
        is ComputeStatus.UNAVAILABLE
    )


def test_powl_footprints_use_partial_order_semantics_and_retain_model_kind():
    leaves = tuple(POWLNode("activity", a) for a in "ABC")
    model = POWLNode("partial_order", children=leaves, order=((0, 2), (1, 2)))
    result = discover_model_footprints(model, ModelFootprintSpec(behavior="accepting"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.model_kind == "powl"
    assert set(result.value.start_activities) == {"A", "B"}
    assert result.value.end_activities == ("C",)
    assert set(result.value.directly_follows) == {
        ("A", "B"),
        ("B", "A"),
        ("A", "C"),
        ("B", "C"),
    }
    assert result_from_json(result_json_bytes(result)) == result
    limited = discover_model_footprints(model, ModelFootprintSpec(max_states=1))
    assert limited.status is ComputeStatus.PARTIAL
    assert limited.value.sequence is None
