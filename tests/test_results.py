"""Native result schemas, round-trip provenance and invalid input boundaries."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest

from pix.api import (
    AlignmentSpec,
    DiscoverySpec,
    ExecutionSpec,
    OCDFGSpec,
    ReplaySpec,
    TemporalSpec,
    TraceSpec,
    VariantSpec,
    align_traces,
    discover_dfg,
    discover_executions,
    discover_ocdfg,
    discover_process_tree,
    discover_variants,
    measure_temporal,
    process_tree_to_petri_net,
    reconstruct_traces,
    replay_traces,
)
from pix.results import (
    read_result,
    result_document,
    result_from_json,
    result_json_bytes,
    write_result,
)


def _resign(document):
    body = {key: value for key, value in document.items() if key != "document_digest"}
    encoded = json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    document["document_digest"] = (
        "pix.analysis-result.v1:sha256:" + sha256(encoded).hexdigest()
    )
    return json.dumps(document)


@pytest.fixture
def native_results(native_log):
    traces = reconstruct_traces(native_log, TraceSpec("Order"))
    executions = discover_executions(native_log, ExecutionSpec("connected_components"))
    tree = discover_process_tree(traces, DiscoverySpec())
    net = process_tree_to_petri_net(tree.value)
    return (
        traces,
        discover_dfg(native_log, TraceSpec("Order")),
        discover_ocdfg(native_log, OCDFGSpec(("Order", "Package"))),
        measure_temporal(native_log, TemporalSpec("Order")),
        executions,
        discover_variants(executions, VariantSpec()),
        tree,
        align_traces(traces, net, AlignmentSpec()),
        replay_traces(traces, net, ReplaySpec()),
        align_traces(traces, net, AlignmentSpec(max_states=1)),
        reconstruct_traces(native_log, TraceSpec("unknown")),
        measure_temporal(native_log, TemporalSpec("Order", start_attribute="missing")),
    )


@pytest.mark.parametrize("index", range(12))
def test_all_result_kinds_roundtrip_including_partial(native_results, index, tmp_path):
    result = native_results[index]
    blob = result_json_bytes(result)
    restored = result_from_json(blob)
    assert restored == result
    assert result_json_bytes(restored) == blob
    path = write_result(result, tmp_path / f"result-{index}.json")
    assert read_result(path) == result


def test_publication_never_overwrites_without_request(native_results, tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("original")
    with pytest.raises(FileExistsError):
        write_result(native_results[0], path)
    assert path.read_text() == "original"
    assert not list(tmp_path.glob(".pix-result-*"))
    write_result(native_results[0], path, overwrite=True)
    assert read_result(path) == native_results[0]


def test_corrupted_payload_is_rejected(native_results):
    document = result_document(native_results[1])
    document["computation"]["value"]["object_count"] = 999
    with pytest.raises(ValueError, match="digest mismatch"):
        result_from_json(json.dumps(document))


def test_valid_checksum_does_not_bypass_field_types(native_results):
    document = result_document(native_results[1])
    document["computation"]["value"]["object_count"] = True
    with pytest.raises(ValueError, match="expected int"):
        result_from_json(_resign(document))


def test_valid_checksum_does_not_bypass_request_identity(native_results):
    document = result_document(native_results[0])
    document["computation"]["spec"]["object_type"] = "SomethingElse"
    with pytest.raises(ValueError, match="identity"):
        result_from_json(_resign(document))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda doc: doc.update(version="999"),
        lambda doc: doc.update(payload_kind="wrong"),
        lambda doc: doc["computation"].update(extra="surprise"),
        lambda doc: doc["computation"]["value"].update(extra="surprise"),
        lambda doc: doc["computation"].update(operator_id="external.evil"),
        lambda doc: doc["computation"].update(operator_version="999"),
    ],
)
def test_unknown_contracts_do_not_load(native_results, mutation):
    document = result_document(native_results[0])
    mutation(document)
    with pytest.raises(ValueError):
        result_from_json(_resign(document))


@pytest.mark.parametrize("text", ['{"format":"a","format":"a"}', '{"x":NaN}', "[]"])
def test_bad_json_boundaries(text):
    with pytest.raises(ValueError):
        result_from_json(text)


def test_forged_inmemory_result_identity_does_not_serialize(native_results):
    result = replace(native_results[0], computation_id="not-the-request-hash")
    with pytest.raises(ValueError, match="identity"):
        result_json_bytes(result)


def test_postcommit_cleanup_failure_preserves_publication(native_results, tmp_path):
    with patch.object(Path, "unlink", side_effect=PermissionError("cleanup denied")):
        publication = write_result(native_results[0], tmp_path / "published.json")
    assert read_result(publication) == native_results[0]
    assert publication.cleanup_issues[0].message == "cleanup denied"
    assert publication.cleanup_issues[0].path.parent == tmp_path


def test_precommit_cleanup_does_not_mask_primary_failure(native_results, tmp_path):
    target = tmp_path / "existing.json"
    target.write_text("original")
    with patch.object(Path, "unlink", side_effect=PermissionError("cleanup denied")):
        with pytest.raises(FileExistsError) as raised:
            write_result(native_results[0], target)
    assert target.read_text() == "original"
    assert raised.value.cleanup_issues[0].message == "cleanup denied"
