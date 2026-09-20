from dataclasses import replace

from pix.case_centric.trace_fit import TraceFitSpec, check_trace_fit
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputeStatus
from pix.event_log import case_log_from_activity_text
from pix.results import result_from_json, result_json_bytes


def test_fit_deviation_and_limit_are_distinct_for_tree_and_petri_net():
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    for model in (tree, process_tree_to_petri_net(tree)):
        accepted = check_trace_fit(case_log_from_activity_text('[["A","B"]]'), model)
        assert accepted.value.fitting is True
        assert accepted.value.reason == "accepted"
        assert result_from_json(result_json_bytes(accepted)) == accepted
        rejected = check_trace_fit(case_log_from_activity_text('[["A","C"]]'), model)
        assert rejected.value.fitting is False
        limited = check_trace_fit(
            case_log_from_activity_text('[["A","B"]]'),
            model,
            TraceFitSpec(max_states=1),
        )
        assert limited.status is ComputeStatus.PARTIAL
        assert limited.value.fitting is None
        assert result_from_json(result_json_bytes(limited)) == limited


def test_empty_trace_and_invalid_population():
    silent = ProcessTree("tau")
    assert (
        check_trace_fit(case_log_from_activity_text("[[]]"), silent).value.fitting
        is True
    )
    log = case_log_from_activity_text("[[], []]")
    assert check_trace_fit(log, silent).status is ComputeStatus.INVALID_INPUT
    assert (
        check_trace_fit(replace(log, traces=()), silent).status
        is ComputeStatus.INVALID_INPUT
    )
