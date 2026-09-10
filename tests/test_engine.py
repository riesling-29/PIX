"""Stage integration: explicit requests share input but retain independent outcomes."""

from unittest.mock import patch

import pytest

from pix.api import (
    ComputationContext,
    ComputeStatus,
    DFGRequest,
    ExecutionRequest,
    ExecutionSpec,
    OCDFGRequest,
    OCDFGSpec,
    TemporalRequest,
    TemporalSpec,
    TraceRequest,
    TraceSpec,
    VariantRequest,
    VariantSpec,
    compute,
)
from pix.ocel import E2O, OCEL, canonical_digest


def test_engine_shares_one_context_and_preserves_request_order(native_log):
    original = canonical_digest(native_log)
    execution = ExecutionSpec("connected_components", object_types=("Order", "Package"))
    requests = (
        TraceRequest(TraceSpec("Order")),
        DFGRequest(TraceSpec("Order")),
        OCDFGRequest(OCDFGSpec(("Order", "Package"))),
        TemporalRequest(TemporalSpec("Order")),
        ExecutionRequest(execution),
        VariantRequest(execution, VariantSpec()),
    )
    with patch.object(
        ComputationContext, "build", wraps=ComputationContext.build
    ) as prepare:
        results = compute(native_log, requests=requests)
    assert prepare.call_count == 1
    assert [r.operator_id for r in results] == [
        "pix.reconstruct_traces",
        "pix.discover_dfg",
        "pix.discover_ocdfg",
        "pix.measure_temporal",
        "pix.discover_executions",
        "pix.discover_variants",
    ]
    assert all(result.status is ComputeStatus.COMPUTED for result in results)
    assert all(result.source_digest == original.identifier for result in results)
    assert results[1].parent_computation_ids == (results[0].computation_id,)
    assert results[-1].parent_computation_ids == (results[-2].computation_id,)
    assert canonical_digest(native_log) == original


def test_failure_does_not_hide_following_success(native_log):
    bad, good = compute(
        native_log,
        requests=(
            TraceRequest(TraceSpec("unknown")),
            DFGRequest(TraceSpec("Order")),
        ),
    )
    assert bad.status is ComputeStatus.UNAVAILABLE and bad.value is None
    assert good.status is ComputeStatus.COMPUTED and good.value.edges


def test_invalid_input_returns_evidence_for_every_operator():
    log = OCEL(e2o=(E2O("missing-event", "missing-object", ""),))
    results = compute(
        log,
        requests=(
            TraceRequest(TraceSpec("Order")),
            DFGRequest(TraceSpec("Order")),
            OCDFGRequest(OCDFGSpec(("Order",))),
            TemporalRequest(TemporalSpec("Order")),
            ExecutionRequest(ExecutionSpec("connected_components")),
            VariantRequest(ExecutionSpec("connected_components"), VariantSpec()),
        ),
    )
    assert all(result.status is ComputeStatus.INVALID_INPUT for result in results)
    assert all(result.source_digest is None and result.issues for result in results)
    assert all(
        any("dangling" in issue.code for issue in result.issues) for result in results
    )


@pytest.mark.parametrize("requests", [(), [], (object(),)])
def test_no_inferred_or_untyped_requests(native_log, requests):
    with pytest.raises((TypeError, ValueError)):
        compute(native_log, requests=requests)


@pytest.mark.parametrize(
    "request_type",
    [TraceRequest, DFGRequest, OCDFGRequest, TemporalRequest, ExecutionRequest],
)
def test_request_rejects_wrong_spec(request_type):
    with pytest.raises(TypeError):
        request_type(object())
