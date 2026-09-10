"""Real native model analysis retains definitions and evidence across JSON I/O."""

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from pix.compute.constraints import evaluate_constraints
from pix.compute.discovery import discover_process_tree, process_tree_to_petri_net
from pix.compute.object_conformance import align_object_log
from pix.compute.object_context import measure_object_context
from pix.compute.ocpn_discovery import discover_ocpn
from pix.compute.precision import measure_prefix_precision
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.constraint import (
    ConstraintSpec,
    CountRule,
    NotCoexistenceRule,
    PrecedenceRule,
    ResponseRule,
    TimedResponseRule,
)
from pix.contracts.discovery import DiscoverySpec
from pix.contracts.object_conformance import ObjectAlignmentSpec
from pix.contracts.object_context import ObjectContextSpec
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.precision import PrefixPrecisionSpec
from pix.contracts.result import ComputeStatus
from pix.models import ModelArtifact, read_model, write_model
from pix.results import (
    read_result,
    result_document,
    result_from_json,
    result_json_bytes,
    write_result,
)
from pix.viewer import build_model_graph, export_html


@pytest.fixture
def extended_results(native_log):
    traces = reconstruct_traces(native_log, TraceSpec("Order"))
    tree = discover_process_tree(traces, DiscoverySpec())
    net = process_tree_to_petri_net(tree.value)
    ocpn = discover_ocpn(
        native_log,
        OCPNDiscoverySpec(("Order", "Package"), "observed_range", "unique_activity"),
    )
    assert ocpn.status is ComputeStatus.COMPUTED, ocpn.issues
    rules = (
        CountRule("created-once", "Create", 1, 1),
        ResponseRule("eventually-shipped", "Create", "Ship"),
        PrecedenceRule("created-before-shipping", "Create", "Ship"),
        NotCoexistenceRule("no-packing", "Create", "Pack"),
        TimedResponseRule(
            "ship-in-nine-minutes", "Create", "Ship", 0, 540_000_000, "any"
        ),
    )
    return (
        ocpn,
        measure_prefix_precision(traces, net, PrefixPrecisionSpec("include")),
        measure_prefix_precision(
            traces, net, PrefixPrecisionSpec("include", max_markings_per_prefix=1)
        ),
        align_object_log(
            native_log, ocpn.value.model, ObjectAlignmentSpec(("Order", "Package"))
        ),
        align_object_log(
            native_log,
            ocpn.value.model,
            ObjectAlignmentSpec(("Order", "Package"), max_states=1),
        ),
        measure_object_context(
            native_log, ocpn.value.model, ObjectContextSpec(("Order", "Package"))
        ),
        measure_object_context(
            native_log,
            ocpn.value.model,
            ObjectContextSpec(("Order", "Package"), max_log_states=1),
        ),
        evaluate_constraints(traces, ConstraintSpec(rules, "closed")),
        evaluate_constraints(
            traces,
            ConstraintSpec((ResponseRule("archive", "Ship", "Archive"),), "open"),
        ),
    )


@pytest.mark.parametrize("index", range(9))
def test_extended_evidence_and_request_roundtrip(extended_results, index, tmp_path):
    result = extended_results[index]
    publication = write_result(result, tmp_path / "result.json")
    restored = read_result(publication)
    assert restored == result
    assert result_json_bytes(restored) == result_json_bytes(result)
    assert restored.spec == result.spec
    assert restored.parent_computation_ids == result.parent_computation_ids


def test_discovered_ocpn_becomes_model_artifact_and_viewer(extended_results, tmp_path):
    result = extended_results[0]
    artifact = ModelArtifact(result.value.model, "discovered", result.computation_id)
    restored = read_model(write_model(artifact, tmp_path / "model.json"))
    assert restored == artifact
    graph = build_model_graph(restored)
    html = export_html(graph, tmp_path / "model.html").read_text(encoding="utf-8")
    assert result.computation_id in html
    assert "observed_range" in result_json_bytes(result).decode("utf-8")
    assert result.value.fitting_witness


def test_new_definition_parameters_are_part_of_identity(extended_results):
    result = extended_results[1]
    changed_spec = replace(
        result.spec,
        parameters=replace(result.spec.parameters, terminal_policy="exclude"),
    )
    with pytest.raises(ValueError, match="identity"):
        result_json_bytes(replace(result, spec=changed_spec))


def test_shared_event_conformance_is_not_counted_once_per_object(extended_results):
    aligned = extended_results[3]
    assert aligned.status is ComputeStatus.COMPUTED
    assert aligned.value.status == "optimal"
    assert aligned.value.cost == 0
    assert sorted(move.event_id for move in aligned.value.moves if move.event_id) == [
        "e1",
        "e2",
        "e3",
        "e4",
        "e5",
        "e6",
        "e7",
    ]
    assert extended_results[4].status is ComputeStatus.PARTIAL
    assert extended_results[4].value.cost is None


def test_context_scope_and_partial_score_survive_persistence(extended_results):
    context = extended_results[5]
    assert context.status is ComputeStatus.COMPUTED
    numerator, denominator = context.value.full_scope_fitness_ratio
    assert numerator == denominator > 0
    limited = extended_results[6]
    assert limited.status is ComputeStatus.PARTIAL
    assert limited.value.full_scope_fitness_ratio is None
    assert limited.value.full_scope_precision_ratio is None


def test_rule_types_populations_and_pending_are_distinct(extended_results, tmp_path):
    result = extended_results[7]
    restored = read_result(write_result(result, tmp_path / "rules.json"))
    assert tuple(type(rule) for rule in restored.spec.rules) == (
        CountRule,
        ResponseRule,
        PrecedenceRule,
        NotCoexistenceRule,
        TimedResponseRule,
    )
    timed = next(rule for rule in restored.value.rules if rule.kind == "timed_response")
    assert timed.fulfillment_ratio == (1, 3)
    assert timed.fulfilled_count == 1
    assert timed.violated_count == 2
    pending = extended_results[8]
    assert pending.status is ComputeStatus.PARTIAL
    assert pending.value.rules[0].pending_count == 3
    assert pending.value.rules[0].violated_count == 0


def _redigest(document):
    body = {key: value for key, value in document.items() if key != "document_digest"}
    payload = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    document["document_digest"] = (
        "pix.analysis-result.v1:sha256:" + sha256(payload.encode()).hexdigest()
    )
    return json.dumps(document, ensure_ascii=False)


def test_previous_result_wire_version_remains_readable(extended_results):
    source = extended_results[1]
    document = result_document(source)
    document["version"] = "1.0.0"
    assert result_from_json(_redigest(document)) == source


def test_valid_checksum_cannot_certify_an_impossible_ocpn_witness(extended_results):
    document = result_document(extended_results[0])
    document["computation"]["value"]["model"]["initial_marking"]["tokens"] = []
    with pytest.raises(ValueError):
        result_from_json(_redigest(document))


def test_individually_valid_precision_payload_cannot_change_request_policy(native_log):
    traces = reconstruct_traces(native_log, TraceSpec("Order"))
    tree = discover_process_tree(traces, DiscoverySpec())
    net = process_tree_to_petri_net(tree.value)
    include = measure_prefix_precision(traces, net, PrefixPrecisionSpec("include"))
    exclude = measure_prefix_precision(traces, net, PrefixPrecisionSpec("exclude"))
    forged = replace(
        include, value=exclude.value, status=exclude.status, issues=exclude.issues
    )
    with pytest.raises(ValueError, match="policies disagree"):
        result_json_bytes(forged)
    document = result_document(include)
    document["computation"]["value"] = result_document(exclude)["computation"]["value"]
    with pytest.raises(ValueError, match="policies disagree"):
        result_from_json(_redigest(document))


@pytest.mark.parametrize("index", (4, 6, 8))
def test_incomplete_evidence_cannot_be_published_as_computed(extended_results, index):
    partial = extended_results[index]
    assert partial.status is ComputeStatus.PARTIAL
    with pytest.raises(ValueError, match="status disagrees"):
        result_json_bytes(replace(partial, status=ComputeStatus.COMPUTED))
