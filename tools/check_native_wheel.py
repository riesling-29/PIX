"""Verify an installed PIX wheel without source-tree or optional dependencies.

Run using a clean wheel-installed interpreter with ``python -I`` and an external
working directory. This smoke check uses only the Python standard library and
the installed PIX package. It does not replace the algorithm or browser suites.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.resources
import json
import re
import sys
import sysconfig
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pix
from pix.api import (
    AlignmentSpec,
    ComputeStatus,
    ConstraintSpec,
    CountRule,
    DiscoverySpec,
    ExecutionSpec,
    ModelArtifact,
    NotCoexistenceRule,
    ObjectAlignmentSpec,
    ObjectContextSpec,
    OCDFGSpec,
    OCPNDiscoverySpec,
    PrecedenceRule,
    PrefixPrecisionSpec,
    ResponseRule,
    TemporalSpec,
    TimedResponseRule,
    TraceSpec,
    VariantSpec,
    align_object_log,
    align_traces,
    discover_dfg,
    discover_executions,
    discover_ocdfg,
    discover_ocpn,
    discover_process_tree,
    discover_variants,
    evaluate_constraints,
    export_ocel,
    measure_object_context,
    measure_prefix_precision,
    measure_temporal,
    process_tree_to_petri_net,
    read_model,
    read_ocel,
    read_result,
    reconstruct_traces,
    replay_traces,
    result_document,
    write_model,
    write_result,
)
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.ocel import (
    E2O,
    OCEL,
    Event,
    EventType,
    Object,
    ObjectType,
    canonical_digest,
)
from pix.viewer import build_graph, build_model_graph, export_html


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sample_log() -> OCEL:
    start = datetime(2026, 9, 9, 9, tzinfo=timezone.utc)
    return OCEL(
        event_types=(EventType("Receive"), EventType("Ship")),
        object_types=(ObjectType("Order"), ObjectType("Package")),
        events=(
            Event("e1", "Receive", start),
            Event("e2", "Ship", start + timedelta(minutes=5)),
        ),
        objects=(
            Object("o1", "Order"),
            Object("o2", "Order"),
            Object("p1", "Package"),
        ),
        e2o=tuple(
            E2O(event_id, object_id, "participates")
            for event_id in ("e1", "e2")
            for object_id in ("o1", "o2", "p1")
        ),
    )


def check_native_pipeline(output: Path) -> dict[str, object]:
    """Exercise the public installed API; callable alone during smoke development."""
    output.mkdir(parents=True, exist_ok=True)
    log = sample_log()
    ocel_roundtrips = {}
    for format_name in ("json", "xml", "sqlite"):
        path = output / ("source." + format_name)
        publication = export_ocel(log, path, format=format_name, overwrite=True)
        restored = read_ocel(path)
        require(publication.roundtrip == "passed", f"Unverified {format_name} export")
        require(
            canonical_digest(restored) == canonical_digest(log), "OCEL digest changed"
        )
        ocel_roundtrips[format_name] = publication.roundtrip

    traces = reconstruct_traces(restored, TraceSpec("Order"))
    require(traces.status is ComputeStatus.COMPUTED, "Trace reconstruction failed")
    tree = discover_process_tree(traces, DiscoverySpec(algorithm="pix.im.v1"))
    require(tree.status is ComputeStatus.COMPUTED, "Native IM discovery failed")
    net = process_tree_to_petri_net(tree.value)
    alignment = align_traces(traces, net, AlignmentSpec())
    require(alignment.status is ComputeStatus.COMPUTED, "Alignment incomplete")
    require(alignment.value.coverage.optimal == 2, "Unexpected aligned trace count")
    require(
        alignment.value.total_cost == 0, "Observed traces do not fit discovered model"
    )
    executions = discover_executions(restored, ExecutionSpec("connected_components"))
    ocdfg = discover_ocdfg(restored, OCDFGSpec(("Order", "Package")))
    ocpn_spec = OCPNDiscoverySpec(
        ("Order", "Package"),
        "observed_range",
        "unique_activity",
        classic_algorithm="pix.im.v1",
    )
    ocpn = discover_ocpn(restored, ocpn_spec)
    require(ocpn.status is ComputeStatus.COMPUTED, "OCPN discovery incomplete")
    object_net = ocpn.value.model
    object_spec = ObjectAlignmentSpec(("Order", "Package"))
    joint_alignment = align_object_log(restored, object_net, object_spec)
    require(
        joint_alignment.status is ComputeStatus.COMPUTED
        and joint_alignment.value.status == "optimal",
        "Joint object alignment incomplete",
    )
    require(joint_alignment.value.cost == 0, "Discovered OCPN does not fit sample")
    require(
        joint_alignment.value.move_counts.synchronous == len(log.events)
        and joint_alignment.value.move_counts.log == 0
        and joint_alignment.value.move_counts.model == 0,
        "Joint alignment must consume both events with their exact participants",
    )
    prefix = measure_prefix_precision(traces, net, PrefixPrecisionSpec("include"))
    context_spec = ObjectContextSpec(("Order", "Package"))
    context = measure_object_context(restored, object_net, context_spec)
    rules = ConstraintSpec(
        (
            CountRule("one-receive", "Receive", 1, 1, kind="count"),
            ResponseRule("receive-then-ship", "Receive", "Ship", kind="response"),
            PrecedenceRule("receive-before-ship", "Receive", "Ship", kind="precedence"),
            NotCoexistenceRule(
                "demonstrate-violation", "Receive", "Ship", kind="not_coexistence"
            ),
            TimedResponseRule(
                "ship-within-ten-minutes",
                "Receive",
                "Ship",
                0,
                600_000_000,
                "any",
                kind="timed_response",
            ),
        ),
        "closed",
    )
    constraints = evaluate_constraints(traces, rules)
    require(
        constraints.status is ComputeStatus.COMPUTED
        and len(constraints.value.rules) == 5,
        "All five constraint kinds must be evaluated",
    )
    rule_results = {rule.kind: rule for rule in constraints.value.rules}
    require(
        rule_results["not_coexistence"].violated_object_count == 2
        and all(
            rule.fulfilled_object_count == 2
            for kind, rule in rule_results.items()
            if kind != "not_coexistence"
        ),
        "Rule evidence must preserve the intentional violation and fulfillments",
    )
    results = {
        "traces": traces,
        "dfg": discover_dfg(restored, TraceSpec("Order")),
        "ocdfg": ocdfg,
        "temporal": measure_temporal(restored, TemporalSpec("Order")),
        "executions": executions,
        "variants": discover_variants(executions, VariantSpec()),
        "process-tree": tree,
        "alignment": alignment,
        "replay": replay_traces(traces, net),
        "ocpn-discovery": ocpn,
        "object-alignment": joint_alignment,
        "prefix-precision": prefix,
        "object-context": context,
        "constraints": constraints,
    }
    require(
        len({result.operator_id for result in results.values()}) == 14,
        "Smoke must cover 14 distinct analytical result kinds",
    )
    result_roundtrips = {}

    def roundtrip(name, result):
        path = write_result(result, output / (name + ".json"), overwrite=True)
        require(read_result(path) == result, f"Result changed after roundtrip: {name}")
        document = result_document(result)
        result_roundtrips[name] = {
            "operator_id": result.operator_id,
            "status": result.status.value,
            "payload_kind": document["payload_kind"],
            "format_version": document["version"],
            "computation_id": result.computation_id,
            "roundtrip": "passed",
        }

    for name, result in results.items():
        require(
            result.status is ComputeStatus.COMPUTED, f"Incomplete smoke result: {name}"
        )
        roundtrip(name, result)

    limited_alignment = align_object_log(
        restored, object_net, replace(object_spec, max_states=1)
    )
    require(
        limited_alignment.status is ComputeStatus.PARTIAL,
        "Bounded joint alignment must preserve partial status",
    )
    require(
        limited_alignment.value.cost is None,
        "Truncated alignment must not invent an optimal cost",
    )
    roundtrip("object-alignment-limited", limited_alignment)

    large_objects = tuple(Object(f"o{index:05d}", "Order") for index in range(15000))
    large_log = OCEL(object_types=(ObjectType("Order"),), objects=large_objects)
    large_net = ObjectCentricPetriNet(
        places=(TypedPlace("received", "Order"),),
        transitions=(Transition("receive", "Receive"),),
        arcs=(ObjectArc("receive", "received", True, 0, None),),
        initial_marking=ObjectMarking(()),
        final_marking=ObjectMarking((ObjectToken("received", "o00000"),)),
        objects=tuple((obj.id, obj.type) for obj in large_objects),
    )
    digit_limit_before = getattr(sys, "get_int_max_str_digits", lambda: None)()
    large_alignment = align_object_log(
        large_log, large_net, ObjectAlignmentSpec(("Order",), max_bindings=1)
    )
    require(
        large_alignment.status is ComputeStatus.PARTIAL
        and large_alignment.value.status == "binding_limit"
        and large_alignment.value.max_enabled_binding_count == 2**15000,
        "Large exact binding count must remain available in a bounded result",
    )
    roundtrip("object-alignment-large-count", large_alignment)
    require(
        getattr(sys, "get_int_max_str_digits", lambda: None)() == digit_limit_before,
        "Result persistence must not change the process-wide integer digit limit",
    )

    invalid_log = replace(log, events=log.events + (log.events[0],))
    invalid_traces = reconstruct_traces(invalid_log, TraceSpec("Order"))
    invalid_results = {
        "ocpn-discovery-invalid": discover_ocpn(invalid_log, ocpn_spec),
        "object-alignment-invalid": align_object_log(
            invalid_log, object_net, object_spec
        ),
        "prefix-precision-invalid": measure_prefix_precision(
            invalid_traces, net, PrefixPrecisionSpec("include")
        ),
        "object-context-invalid": measure_object_context(
            invalid_log, object_net, context_spec
        ),
        "constraints-invalid": evaluate_constraints(invalid_traces, rules),
    }
    for name, result in invalid_results.items():
        require(
            result.status is ComputeStatus.INVALID_INPUT,
            f"Invalid OCEL status was not preserved: {name}",
        )
        require(
            result.value is None and bool(result.issues),
            f"Invalid OCEL must retain diagnostics without payload: {name}",
        )
        roundtrip(name, result)

    artifacts = {
        "model": ModelArtifact(net, "discovered", tree.computation_id),
        "ocpn": ModelArtifact(object_net, "discovered", ocpn.computation_id),
    }
    for name, artifact in artifacts.items():
        path = write_model(artifact, output / (name + ".model.json"), overwrite=True)
        require(read_model(path) == artifact, f"Model changed after roundtrip: {name}")
    graphs = {"ocdfg": build_graph(ocdfg)}
    graphs.update(
        {name: build_model_graph(artifact) for name, artifact in artifacts.items()}
    )
    html_artifacts = {}
    for name, graph in graphs.items():
        path = export_html(graph, output / (name + ".html"), overwrite=True)
        html_bytes = path.read_bytes()
        html_text = html_bytes.decode("utf-8")
        require("pixViewerReady" in html_text, "Missing viewer runtime")
        require("pix-viewer-license" in html_text, "Missing bundled license")
        require(
            re.search(r"<(?:script|link)\b[^>]*(?:src|href)\s*=", html_text, re.I)
            is None,
            "Offline HTML unexpectedly references an external script or stylesheet",
        )
        html_artifacts[name] = {
            "path": str(path),
            "bytes": len(html_bytes),
            "sha256": digest(html_bytes),
        }
    return {
        "ocel_roundtrips": ocel_roundtrips,
        "result_roundtrips": result_roundtrips,
        "distinct_computed_result_kinds": len(results),
        "invalid_input_roundtrips": len(invalid_results),
        "partial_result_roundtrips": 2,
        "large_exact_binding_count_bits": large_alignment.value.max_enabled_binding_count.bit_length(),
        "integer_digit_limit_unchanged": True,
        "classic_discovery_algorithm": tree.spec.algorithm,
        "optimal_traces": alignment.value.coverage.optimal,
        "classical_total_cost": alignment.value.total_cost,
        "joint_alignment_status": joint_alignment.value.status,
        "joint_alignment_cost": joint_alignment.value.cost,
        "joint_alignment_synchronous_events": joint_alignment.value.move_counts.synchronous,
        "prefix_precision_ratio": prefix.value.whole_log_ratio,
        "object_context_fitness_ratio": context.value.full_scope_fitness_ratio,
        "object_context_precision_ratio": context.value.full_scope_precision_ratio,
        "constraint_kinds": sorted(rule_results),
        "model_roundtrips": {name: "passed" for name in artifacts},
        "offline_html": html_artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[1]
    installed_path = Path(pix.__file__).resolve()
    purelib = Path(sysconfig.get_path("purelib")).resolve()
    require(sys.flags.isolated == 1, "Run the smoke check with python -I")
    require(sys.prefix != sys.base_prefix, "Use an isolated virtual environment")
    require(
        installed_path.is_relative_to(purelib), "PIX was not loaded from site-packages"
    )
    require(
        not Path.cwd().resolve().is_relative_to(source_root),
        "Run from a working directory outside the source checkout",
    )
    require(
        not any(
            entry and Path(entry).resolve() == source_root / "src" for entry in sys.path
        ),
        "Source-tree import path unexpectedly present",
    )
    distribution = importlib.metadata.distribution("pix")
    require(distribution.version == "0.4.0", "Unexpected installed PIX version")
    require(
        pix.__version__ == distribution.version, "Package version differs from metadata"
    )
    requirements = distribution.requires or []
    require(
        all(re.search(r";\s*extra\s*==\s*['\"]", item) for item in requirements),
        "Unexpected runtime dependency in wheel metadata",
    )
    installed_distributions = sorted(
        package.metadata["Name"] for package in importlib.metadata.distributions()
    )
    require(
        [name.lower() for name in installed_distributions] == ["pix"],
        "Smoke environment must contain only PIX",
    )
    expected_assets = (
        "viewer.js",
        "layout.js",
        "viewer.css",
        "model.css",
        "vendor/elk.bundled.js",
        "vendor/ELK-LICENSE.md",
        "vendor/provenance.json",
    )
    assets = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in expected_assets:
            packaged = archive.read("pix/viewer/assets/" + name)
            installed = (
                importlib.resources.files("pix.viewer")
                .joinpath("assets", *name.split("/"))
                .read_bytes()
            )
            require(bool(installed), f"Empty viewer asset: {name}")
            require(
                installed == packaged, f"Installed asset differs from wheel: {name}"
            )
            assets[name] = {"bytes": len(installed), "sha256": digest(installed)}

    vendor_provenance = json.loads(
        importlib.resources.files("pix.viewer")
        .joinpath("assets", "vendor", "provenance.json")
        .read_text(encoding="utf-8")
    )
    require(vendor_provenance["version"] == "0.12.0", "Unexpected ELK version")
    for entry in vendor_provenance["files"]:
        recorded = assets["vendor/" + entry["file"]]
        require(
            recorded == {"bytes": entry["bytes"], "sha256": entry["sha256"]},
            "Vendor provenance does not match bundled asset",
        )

    source_files = {
        "pix/" + path.relative_to(source_root / "src" / "pix").as_posix(): path
        for path in (source_root / "src" / "pix").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }
    excluded_source_documentation = {}
    # This developer guide is not runtime package data in pyproject.toml.
    # Keep the exception explicit: unexpected omitted modules/assets must fail.
    documentation_name = "pix/viewer/README.md"
    if documentation_name in source_files:
        documentation_bytes = source_files.pop(documentation_name).read_bytes()
        excluded_source_documentation[documentation_name] = {
            "reason": "Developer documentation outside declared runtime package data",
            "bytes": len(documentation_bytes),
            "sha256": digest(documentation_bytes),
        }
    source_byte_matches = {}
    with zipfile.ZipFile(wheel) as archive:
        package_members = {
            name for name in archive.namelist() if name.startswith("pix/")
        }
        require(
            package_members == set(source_files),
            "Wheel package file set differs from current source",
        )
        for name, source_path in sorted(source_files.items()):
            source_bytes = source_path.read_bytes()
            packaged = archive.read(name)
            installed = (purelib / name).read_bytes()
            require(
                source_bytes == packaged == installed,
                f"Source, wheel and installed bytes differ: {name}",
            )
            source_byte_matches[name] = {
                "bytes": len(source_bytes),
                "sha256": digest(source_bytes),
            }
    native_pipeline = check_native_pipeline(output)

    wheel_bytes = wheel.read_bytes()
    evidence = {
        "status": "passed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "interpreter": sys.executable,
        "working_directory": str(Path.cwd()),
        "installed_pix": str(installed_path),
        "installed_distributions": installed_distributions,
        "version": distribution.version,
        "smoke_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": digest(Path(__file__).read_bytes()),
        },
        "wheel": {
            "path": str(wheel),
            "bytes": len(wheel_bytes),
            "sha256": digest(wheel_bytes),
        },
        "requires_dist": requirements,
        "unconditional_runtime_requirements": [],
        "viewer_assets": assets,
        "source_wheel_installed_byte_match": {
            "status": "passed",
            "package_file_count": len(source_byte_matches),
            "files": source_byte_matches,
            "excluded_source_documentation": excluded_source_documentation,
        },
        "viewer_vendor": {
            "package": vendor_provenance["package"],
            "version": vendor_provenance["version"],
            "selected_license": vendor_provenance["selected_license"],
            "recorded_hashes_match": True,
        },
        "native_pipeline": native_pipeline,
        "scope": "Installed-package smoke; algorithm and browser suites are separate",
    }
    evidence_path = output / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "passed", "evidence": str(evidence_path)}))


if __name__ == "__main__":
    main()
