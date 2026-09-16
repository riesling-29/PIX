"""Smoke a wheel-only PIX installation from outside its source checkout.

Run with ``python -I`` in an isolated environment containing only the extracted
or installed PIX wheel. Explicit embedded-Python ``._pth`` environments are
supported. This checks packaging and short native pipelines, not algorithm
equivalence to reference libraries or all optional backends.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import pkgutil
import re
import sys
import traceback
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_environment(wheel: Path, site: Path, source: Path) -> dict:
    require(sys.flags.isolated == 1, "Run using python -I")
    checkout = Path(__file__).resolve().parents[1]
    require(
        not any(
            Path.cwd().resolve().is_relative_to(root) for root in (source, checkout)
        ),
        "Use an external cwd",
    )
    require(
        all(
            not Path(entry).resolve().is_relative_to(root / "src")
            for entry in sys.path
            if entry
            for root in (source, checkout)
        ),
        "Source checkout appears on sys.path",
    )
    import pix

    installed = Path(pix.__file__).resolve()
    require(installed.is_relative_to(site), "PIX was not loaded from the wheel site")
    distributions = sorted(
        (item.metadata["Name"].lower(), item.version)
        for item in importlib.metadata.distributions()
    )
    require(
        [name for name, _ in distributions] == ["pix"],
        "The smoke environment must contain only PIX",
    )
    distribution = importlib.metadata.distribution("pix")
    require(
        pix.__version__ == distribution.version, "Package/metadata version mismatch"
    )
    require(
        all(
            re.search(r";\s*extra\s*==\s*['\"]", value)
            for value in (distribution.requires or [])
        ),
        "The native wheel unexpectedly requires a runtime dependency",
    )
    optional = ("pm4py", "ocpa", "numpy", "scipy", "torch", "transformers", "gensim")
    require(
        all(importlib.util.find_spec(name) is None for name in optional),
        "An optional or reference dependency is available in the smoke environment",
    )
    source_files = {
        "pix/" + item.relative_to(source / "src" / "pix").as_posix(): item
        for item in (source / "src" / "pix").rglob("*")
        if item.is_file() and "__pycache__" not in item.parts
    }
    source_files.pop("pix/viewer/README.md", None)
    matches = {}
    with zipfile.ZipFile(wheel) as archive:
        members = {
            item.filename
            for item in archive.infolist()
            if not item.is_dir() and item.filename.startswith("pix/")
        }
        require(
            members == set(source_files),
            f"Source/wheel file mismatch: missing={sorted(set(source_files) - members)}, "
            f"extra={sorted(members - set(source_files))}",
        )
        for name in sorted(members):
            packaged = archive.read(name)
            require(
                packaged == source_files[name].read_bytes(),
                f"Wheel differs from source snapshot: {name}",
            )
            require(
                packaged == site.joinpath(*name.split("/")).read_bytes(),
                f"Installed file differs from wheel: {name}",
            )
            matches[name] = {"bytes": len(packaged), "sha256": sha256(packaged)}
    return {
        "python": sys.version,
        "executable": sys.executable,
        "isolated": sys.flags.isolated,
        "cwd": str(Path.cwd()),
        "checkout": str(checkout),
        "source_snapshot": str(source),
        "sys_path": sys.path,
        "pix_path": str(installed),
        "version": distribution.version,
        "distributions": distributions,
        "optional_dependencies_absent": list(optional),
        "source_wheel_install_matches": matches,
    }


def check_native_mining(output: Path) -> dict:
    import pix.case_centric as cc
    import pix.object_centric as oc
    from pix.api import export_ocel, process_tree_to_petri_net, read_ocel
    from pix.case_centric.inductive import InductiveSpec
    from pix.contracts.result import ComputeStatus
    from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
    from pix.ocel import (
        E2O,
        OCEL,
        Event,
        EventType,
        Object,
        ObjectType,
        canonical_digest,
    )
    from pix.results import read_result, write_result

    imported_modules = []
    for namespace in (cc, oc):
        for module in pkgutil.walk_packages(
            namespace.__path__, namespace.__name__ + "."
        ):
            importlib.import_module(module.name)
            imported_modules.append(module.name)
        for name in namespace.__all__:
            getattr(namespace, name)

    words = (("A", "B"), ("A", "B"), ("A", "C"))
    cases = CaseLog(
        traces=tuple(
            CaseTrace(
                f"case-{case_index}",
                tuple(
                    CaseEvent(
                        f"c{case_index}-e{event_index}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for event_index, activity in enumerate(word)
                ),
            )
            for case_index, word in enumerate(words)
        )
    )
    dfg = cc.discover_dfg(cases)
    require(dfg.status is ComputeStatus.COMPUTED, "Case DFG incomplete")
    require(
        {(edge.source, edge.target): edge.count for edge in dfg.value.edges}
        == {("A", "B"): 2, ("A", "C"): 1},
        "Wrong case DFG frequencies",
    )
    tree = cc.discover_inductive(cases, InductiveSpec(variant="im"))
    require(tree.status is ComputeStatus.COMPUTED, "Case IM incomplete")
    net = process_tree_to_petri_net(tree.value)
    alignment = cc.align_traces(cases, net)
    require(alignment.status is ComputeStatus.COMPUTED, "Case alignment incomplete")
    require(
        alignment.value.coverage.optimal == 3 and alignment.value.total_cost == 0,
        "The three source-ordered case traces must fit their discovered model",
    )

    start = datetime(2026, 9, 15, 0, tzinfo=timezone.utc)
    log = OCEL(
        event_types=tuple(EventType(name) for name in ("Receive", "Pack", "Ship")),
        object_types=(ObjectType("Order"), ObjectType("Package")),
        events=tuple(
            Event(f"e{index}", name, start + timedelta(minutes=index))
            for index, name in enumerate(("Receive", "Pack", "Ship"), 1)
        ),
        objects=(Object("o1", "Order"), Object("p1", "Package")),
        e2o=(
            E2O("e1", "o1", "participates"),
            E2O("e2", "o1", "participates"),
            E2O("e2", "p1", "participates"),
            E2O("e3", "o1", "participates"),
            E2O("e3", "p1", "participates"),
        ),
    )
    statistics = oc.object_statistics(log)
    require(statistics.status is ComputeStatus.COMPUTED, "OCEL statistics incomplete")
    require(
        (
            statistics.value.source_event_count,
            statistics.value.object_count,
            statistics.value.unique_participation_count,
        )
        == (3, 2, 5),
        "Shared events and event-object participations were conflated",
    )
    relations = oc.discover_object_graph(log)
    require(relations.status is ComputeStatus.COMPUTED, "Object graph incomplete")
    require(
        tuple(
            (edge.source, edge.target, edge.event_ids) for edge in relations.value.edges
        )
        == (("o1", "p1", ("e2", "e3")),),
        "Shared-event relation witnesses changed",
    )
    ocel_path = output / "source.ocel.json"
    export_result = export_ocel(log, ocel_path, format="json", overwrite=True)
    require(export_result.roundtrip == "passed", "OCEL export did not verify roundtrip")
    require(
        canonical_digest(read_ocel(ocel_path)) == canonical_digest(log),
        "Canonical OCEL changed during JSON roundtrip",
    )

    results = {
        "case-dfg": dfg,
        "case-im": tree,
        "case-alignment": alignment,
        "object-statistics": statistics,
        "object-interaction": relations,
    }
    roundtrips = {}
    for name, result in results.items():
        path = write_result(result, output / (name + ".json"), overwrite=True)
        require(read_result(path) == result, f"Result JSON roundtrip changed {name}")
        roundtrips[name] = {
            "operator_id": result.operator_id,
            "status": result.status.value,
            "computation_id": result.computation_id,
        }
    forbidden = ("pm4py", "ocpa", "numpy", "scipy", "torch", "transformers", "gensim")
    require(
        not any(name.split(".")[0] in forbidden for name in sys.modules),
        "Native smoke imported an optional/reference dependency",
    )
    return {
        "namespace_modules_imported": sorted(imported_modules),
        "case_count": len(cases.traces),
        "case_event_count": sum(len(trace.events) for trace in cases.traces),
        "case_timestamps_required": False,
        "case_dfg_frequencies": [["A", "B", 2], ["A", "C", 1]],
        "case_optimal_alignments": alignment.value.coverage.optimal,
        "case_alignment_total_cost": alignment.value.total_cost,
        "ocel_event_count": len(log.events),
        "ocel_object_count": len(log.objects),
        "ocel_unique_participation_count": statistics.value.unique_participation_count,
        "object_interaction_witnesses": ["e2", "e3"],
        "ocel_json_roundtrip": "passed",
        "result_json_roundtrips": roundtrips,
        "optional_reference_imports": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "wheel": str(wheel),
        "wheel_bytes": wheel.stat().st_size,
        "wheel_sha256": sha256(wheel.read_bytes()),
        "success": False,
    }
    try:
        evidence["environment"] = check_environment(
            wheel,
            args.site_packages.resolve(strict=True),
            args.source_root.resolve(strict=True),
        )
        evidence["native_mining"] = check_native_mining(output)
        evidence["success"] = True
    except Exception as exc:
        evidence["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
    (output / "mining-wheel-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "success": evidence["success"],
                "wheel": str(wheel),
                "evidence": str(output / "mining-wheel-evidence.json"),
                "error": evidence.get("error"),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if evidence["success"] else 1)


if __name__ == "__main__":
    main()
