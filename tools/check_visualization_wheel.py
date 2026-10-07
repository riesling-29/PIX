"""Verify installed PIX visualization adapters, JSON, and offline HTML assets.

Run with python -I from outside the checkout in a wheel-only environment. This
checks native Python pipelines and exported HTML contents. Browser execution and
layout interaction are covered by the separate viewer test suites.
"""

from __future__ import annotations

import argparse
import importlib.resources
import importlib.util
import json
import runpy
import sys
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

_HELPERS = runpy.run_path(str(Path(__file__).with_name("check_mining_wheel.py")))
require = _HELPERS["require"]
sha256 = _HELPERS["sha256"]
check_environment = _HELPERS["check_environment"]

VISUALIZATION_FILES = (
    "pix/viewer/visual_contracts.py",
    "pix/viewer/visual_serialization.py",
    "pix/viewer/visualization.py",
    "pix/viewer/visual_case_adapters.py",
    "pix/viewer/visual_object_adapters.py",
    "pix/viewer/visual_model_adapters.py",
    "pix/viewer/visual_model_results.py",
    "pix/viewer/visual_annotations.py",
    "pix/viewer/visual_chevrons.py",
    "pix/viewer/assets/native_geometry.js",
    "pix/viewer/assets/graphviz_geometry.js",
    "pix/viewer/assets/legacy_graphviz.js",
    "pix/viewer/assets/visualization.js",
    "pix/viewer/assets/visualization.css",
    "pix/viewer/assets/vendor/viz-global.js",
    "pix/viewer/assets/vendor/graphviz-provenance.json",
    "pix/viewer/assets/vendor/GRAPHVIZ-LICENSE.txt",
    "pix/viewer/assets/vendor/VIZ-LICENSE.txt",
    "pix/viewer/assets/vendor/EXPAT-LICENSE.txt",
)


class ExportedHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.external_assets: list[tuple[str, str, str]] = []
        self.scripts: list[dict] = []
        self.active_script: dict | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attributes = dict(attrs)
        for attribute in ("src", "href"):
            if tag in ("script", "link", "iframe", "img") and attribute in attributes:
                self.external_assets.append((tag, attribute, attributes[attribute]))
        if tag == "script":
            self.active_script = {"attributes": attributes, "text": ""}
            self.scripts.append(self.active_script)

    def handle_data(self, data: str) -> None:
        if self.active_script is not None:
            self.active_script["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.active_script = None


def check_visualization_pipeline(output: Path) -> dict:
    import pix.case_centric as cc
    import pix.object_centric as oc
    import pix.viewer as viewer
    from pix.case_centric.split_miner import discover_split_miner
    from pix.contracts.discovery import ProcessTree
    from pix.contracts.result import ComputeStatus
    from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
    from pix.models import ModelArtifact, model_document
    from pix.ocel import (
        E2O,
        OCEL,
        Event,
        EventType,
        Object,
        ObjectType,
        canonical_digest,
    )

    output.mkdir(parents=True, exist_ok=True)
    for name in viewer.__all__:
        require(getattr(viewer, name) is not None, f"Missing viewer export: {name}")
    require(
        all(
            importlib.util.find_spec(name) is None
            for name in ("graphviz", "pydot", "pm4py", "ocpa")
        ),
        "A graph/reference dependency is present in the isolated environment",
    )

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
    require(dfg.status is ComputeStatus.COMPUTED, "Case DFG calculation incomplete")
    require(
        {(edge.source, edge.target): edge.count for edge in dfg.value.edges}
        == {("A", "B"): 2, ("A", "C"): 1},
        "Unexpected DFG frequencies",
    )
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    mined_tree = cc.discover_inductive(cases)
    require(mined_tree.status is ComputeStatus.COMPUTED, "Native IM incomplete")
    model_artifact = ModelArtifact(
        mined_tree.value, "discovered", mined_tree.computation_id
    )
    wrapped_model = discover_split_miner(cases)
    require(
        wrapped_model.value is not None and wrapped_model.value.model is not None,
        "Split discovery did not return a real wrapped model",
    )
    start = datetime(2026, 9, 15, tzinfo=timezone.utc)
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
    documents = {
        "case-dfg": viewer.build_visualization(dfg, title='Installed <PIX> & "DFG"'),
        "raw-ocel": viewer.build_visualization(log),
        "process-tree": viewer.build_visualization(tree),
        "model-artifact": viewer.build_visualization(model_artifact),
        "discovery-wrapper": viewer.build_visualization(wrapped_model),
    }
    chevron_rows = (
        ("a", "Start", ("x", "y")),
        ("b", "Short", ("y",)),
        ("c", "Work", ("x",)),
        ("d", "Work", ("x",)),
        ("e", "Join", ("x", "y")),
    )
    chevron_log = OCEL(
        event_types=tuple(
            EventType(name) for name in ("Start", "Short", "Work", "Join")
        ),
        object_types=(ObjectType("Item"),),
        events=tuple(
            Event(event_id, activity, start + timedelta(minutes=index))
            for index, (event_id, activity, _) in enumerate(chevron_rows)
        ),
        objects=(Object("x", "Item"), Object("y", "Item")),
        e2o=tuple(
            E2O(event_id, object_id, "flow")
            for event_id, _, objects in chevron_rows
            for object_id in objects
        ),
    )
    executions = oc.discover_executions(
        chevron_log, oc.ExecutionSpec("connected_components")
    )
    variants = oc.discover_variants(executions, oc.VariantSpec())
    documents["object-variant-chevron"] = viewer.build_variant_visualization(
        executions, variants
    )
    chevron = next(
        panel
        for panel in documents["object-variant-chevron"].panels
        if isinstance(panel, viewer.ChevronPanel)
    )
    require(
        {lane.object_id for lane in chevron.lanes} == {"x", "y"}
        and all(isinstance(lane, viewer.ChevronLane) for lane in chevron.lanes),
        "Chevron lanes must preserve individual objects of the same type",
    )
    require(
        all(isinstance(event, viewer.ChevronEvent) for event in chevron.events),
        "Chevron events must use their native typed contract",
    )
    require(
        {event.id: (event.start, event.end) for event in chevron.events}
        == {"a": (0, 0), "b": (1, 2), "c": (1, 1), "d": (2, 2), "e": (3, 3)},
        "Chevron precedence layers differ from the fork/join hand calculation",
    )
    require(
        (chevron.frequency, chevron.population) == (1, 1),
        "Chevron execution frequency or population changed",
    )
    require(
        next(event.lane_ids for event in chevron.events if event.id == "e")
        == ("x", "y")
        and len([event for event in chevron.events if event.id == "e"]) == 1,
        "The shared join event must retain one identity across both lanes",
    )
    graph_type = viewer.GraphPanel
    dfg_graph = next(
        panel for panel in documents["case-dfg"].panels if isinstance(panel, graph_type)
    )
    labels = {node.id: node.label for node in dfg_graph.nodes}
    visual_counts = {
        (labels[edge.source], labels[edge.target]): next(
            metric.value for metric in edge.metrics if metric.name == "selected count"
        )
        for edge in dfg_graph.edges
    }
    require(
        visual_counts == {("A", "B"): 2, ("A", "C"): 1},
        "The visualization changed the computed case frequencies",
    )
    require(
        documents["case-dfg"].provenance[0].calculation_id == dfg.computation_id,
        "DFG computation identity was lost",
    )
    incidence = next(
        panel for panel in documents["raw-ocel"].panels if isinstance(panel, graph_type)
    )
    require(
        Counter(node.kind for node in incidence.nodes) == {"event": 3, "object": 2},
        "Raw OCEL event/object identities changed",
    )
    require(
        len(incidence.edges) == 5
        and all(edge.kind == "e2o" for edge in incidence.edges),
        "Raw OCEL participation relationships changed",
    )
    require(
        documents["raw-ocel"].provenance[0].source_digest
        == canonical_digest(log).identifier,
        "Raw OCEL canonical identity was lost",
    )
    require(
        all(
            item.calculation_id is None for item in documents["process-tree"].provenance
        ),
        "A raw process tree was falsely attributed to discovery",
    )
    require(
        documents["model-artifact"].provenance[0].calculation_id
        == mined_tree.computation_id,
        "Model artifact discovery identity was lost",
    )
    require(
        documents["discovery-wrapper"].provenance[0].calculation_id
        == wrapped_model.computation_id,
        "Discovery wrapper computation identity was lost",
    )
    embedded_digest = model_document(wrapped_model.value.model)["model_digest"]
    require(
        any(
            item.model_digest == embedded_digest
            for item in documents["discovery-wrapper"].provenance
        ),
        "Discovery wrapper embedded model identity was lost",
    )

    assets = importlib.resources.files("pix.viewer").joinpath("assets")
    native_geometry = assets.joinpath("native_geometry.js").read_text(encoding="utf-8")
    visualization_js = assets.joinpath("visualization.js").read_text(encoding="utf-8")
    visualization_css = assets.joinpath("visualization.css").read_text(encoding="utf-8")
    elk = assets.joinpath("vendor", "elk.bundled.js").read_text(encoding="utf-8")
    viz = assets.joinpath("vendor", "viz-global.js").read_text(encoding="utf-8")
    graphviz_geometry = assets.joinpath("graphviz_geometry.js").read_text(
        encoding="utf-8"
    )
    legacy_graphviz = assets.joinpath("legacy_graphviz.js").read_text(encoding="utf-8")
    graphviz_provenance = json.loads(
        assets.joinpath("vendor", "graphviz-provenance.json").read_text(
            encoding="utf-8"
        )
    )
    require(
        graphviz_provenance["package"]["name"] == "@viz-js/viz"
        and graphviz_provenance["package"]["version"] == "3.30.0"
        and graphviz_provenance["graphviz"]["version"] == "16.0.0",
        "Unexpected Graphviz/Viz.js package versions",
    )
    for item in graphviz_provenance["files"]:
        data = assets.joinpath("vendor", item["name"]).read_bytes()
        require(
            len(data) == item["bytes"] and sha256(data) == item["sha256"],
            f"Graphviz provenance differs from installed asset: {item['name']}",
        )

    def require_graphviz_license(parsed):
        license_payload = json.loads(
            next(
                script["text"]
                for script in parsed.scripts
                if script["attributes"].get("id") == "pix-viewer-license"
            )
        )
        require(
            license_payload["provenance"] == graphviz_provenance,
            "HTML Graphviz provenance differs from the packaged record",
        )
        for key, filename in (
            ("license", "GRAPHVIZ-LICENSE.txt"),
            ("viz_license", "VIZ-LICENSE.txt"),
            ("expat_license", "EXPAT-LICENSE.txt"),
        ):
            require(
                license_payload[key]
                == assets.joinpath("vendor", filename).read_text(encoding="utf-8"),
                f"HTML is missing or changed the {filename} license",
            )

    require(
        "PIXGraphvizGeometry" in visualization_js,
        "Visualization layout no longer references the Graphviz geometry bridge",
    )
    outputs = {}
    for name, document in documents.items():
        require(document.panels, f"No visual panels were created for {name}")
        json_path = output / (name + ".visual.json")
        viewer.write_visualization(document, json_path)
        restored = viewer.read_visualization(json_path)
        require(restored == document, f"Visual JSON roundtrip changed {name}")
        require(
            viewer.visualization_json_bytes(restored) == json_path.read_bytes(),
            f"Visual JSON is not deterministic after {name} roundtrip",
        )
        html_path = viewer.export_html(document, output / (name + ".html"))
        html = html_path.read_text(encoding="utf-8")
        parsed = ExportedHTML()
        parsed.feed(html)
        require(not parsed.external_assets, f"External HTML asset reference: {name}")
        scripts = [script["text"].strip() for script in parsed.scripts]
        require(
            all(
                asset.strip() in scripts
                for asset in (native_geometry, viz, graphviz_geometry, visualization_js)
            ),
            f"PIX/Graphviz JS assets were not embedded exactly: {name}",
        )
        require(visualization_css in html, f"Visualization CSS missing: {name}")
        require(
            elk.strip() not in scripts and "new ELK" not in html,
            f"New visualization unexpectedly includes ELK: {name}",
        )
        require(
            "PIXVisualization.mount" in html and "window.pixViewerReady" in html,
            f"Missing visualization bootstrap: {name}",
        )
        require(
            'layoutEngine: "graphviz"' in html,
            f"Graphviz is not the default layout: {name}",
        )
        require_graphviz_license(parsed)
        payload = next(
            script["text"]
            for script in parsed.scripts
            if script["attributes"].get("id") == "pix-visualization-data"
        )
        require(
            json.loads(payload) == json.loads(json_path.read_bytes()),
            f"HTML payload changed the visual JSON: {name}",
        )
        outputs[name] = {
            "status": document.status,
            "panels": [panel.kind for panel in document.panels],
            "json": {
                "path": str(json_path),
                "bytes": json_path.stat().st_size,
                "sha256": sha256(json_path.read_bytes()),
            },
            "html": {
                "path": str(html_path),
                "bytes": html_path.stat().st_size,
                "sha256": sha256(html_path.read_bytes()),
            },
            "visual_json_roundtrip": "passed",
            "html_payload_equality": "passed",
            "exact_pix_and_graphviz_assets_embedded": True,
            "layout_engine": "graphviz",
            "graphviz_license_payload_verified": True,
            "elk_embedded": False,
            "external_assets": parsed.external_assets,
        }

    legacy_result = oc.discover_ocdfg(log, oc.OCDFGSpec(("Order", "Package")))
    require(legacy_result.status is ComputeStatus.COMPUTED, "Legacy OCDFG incomplete")
    legacy_graph = viewer.build_graph(legacy_result)
    legacy_path = viewer.export_html(legacy_graph, output / "legacy-ocdfg.html")
    legacy_html = legacy_path.read_text(encoding="utf-8")
    parsed_legacy = ExportedHTML()
    parsed_legacy.feed(legacy_html)
    require(not parsed_legacy.external_assets, "Legacy HTML gained external assets")
    require(
        all(
            asset.strip()
            in [script["text"].strip() for script in parsed_legacy.scripts]
            for asset in (viz, graphviz_geometry, legacy_graphviz)
        )
        and elk.strip()
        not in [script["text"].strip() for script in parsed_legacy.scripts],
        "Legacy default must embed Graphviz and its bridge without ELK",
    )
    require(
        any(
            script["attributes"].get("id") == "pix-viewer-license"
            for script in parsed_legacy.scripts
        ),
        "Legacy Graphviz provenance missing",
    )
    require(
        'window.PIXViewerLayoutEngine = "graphviz"' in legacy_html,
        "Legacy default engine is not Graphviz",
    )
    require_graphviz_license(parsed_legacy)
    native_path = viewer.export_html(
        documents["case-dfg"], output / "case-dfg-native.html", layout_engine="native"
    )
    native_html = native_path.read_text(encoding="utf-8")
    parsed_native = ExportedHTML()
    parsed_native.feed(native_html)
    native_scripts = [script["text"].strip() for script in parsed_native.scripts]
    require(
        native_geometry.strip() in native_scripts
        and viz.strip() not in native_scripts
        and elk.strip() not in native_scripts
        and 'layoutEngine: "native"' in native_html
        and not parsed_native.external_assets,
        "Explicit native visualization did not preserve its isolated engine choice",
    )
    elk_path = viewer.export_html(
        legacy_graph, output / "legacy-ocdfg-elk.html", layout_engine="elk"
    )
    elk_html = elk_path.read_text(encoding="utf-8")
    parsed_elk = ExportedHTML()
    parsed_elk.feed(elk_html)
    elk_scripts = [script["text"].strip() for script in parsed_elk.scripts]
    require(
        elk.strip() in elk_scripts
        and viz.strip() not in elk_scripts
        and 'window.PIXViewerLayoutEngine = "elk"' in elk_html
        and not parsed_elk.external_assets,
        "Explicit legacy ELK export did not preserve its engine choice",
    )
    for value, engine in ((documents["case-dfg"], "elk"), (legacy_graph, "native")):
        try:
            viewer.render_html(value, layout_engine=engine)
        except ValueError:
            pass
        else:
            raise RuntimeError(
                f"Unsupported document/engine pair was accepted: {engine}"
            )
    forbidden = {
        "graphviz",
        "pydot",
        "pm4py",
        "ocpa",
        "numpy",
        "scipy",
        "torch",
        "transformers",
    }
    require(
        not any(name.split(".")[0] in forbidden for name in sys.modules),
        "Visualization imported an optional or reference dependency",
    )
    return {
        "viewer_export_count": len(viewer.__all__),
        "visual_documents": outputs,
        "case_dfg_preserved": [["A", "B", 2], ["A", "C", 1]],
        "raw_ocel_preserved": {"events": 3, "objects": 2, "participations": 5},
        "model_provenance_preserved": True,
        "chevrons": {
            "objects": ["x", "y"],
            "event_count": len(chevron.events),
            "short_branch_layers": [1, 2],
            "shared_join_lanes": ["x", "y"],
            "frequency": chevron.frequency,
            "population": chevron.population,
        },
        "graphviz_vendor": {
            "package": graphviz_provenance["package"],
            "graphviz": graphviz_provenance["graphviz"],
            "installed_hashes_match": True,
        },
        "legacy_ocdfg": {
            "path": str(legacy_path),
            "bytes": legacy_path.stat().st_size,
            "sha256": sha256(legacy_path.read_bytes()),
            "layout_engine": "graphviz",
            "elk_embedded": False,
            "external_assets": [],
        },
        "explicit_alternatives": {
            "native": str(native_path),
            "legacy_elk": str(elk_path),
            "unsupported_type_engine_pairs_rejected": 2,
        },
        "optional_reference_imports": [],
        "browser_execution_performed": False,
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
        "success": False,
        "wheel": str(wheel),
        "wheel_bytes": wheel.stat().st_size,
        "wheel_sha256": sha256(wheel.read_bytes()),
        "checker_sha256": sha256(Path(__file__).read_bytes()),
        "mining_helper_sha256": sha256(
            Path(__file__).with_name("check_mining_wheel.py").read_bytes()
        ),
    }
    try:
        evidence["environment"] = check_environment(
            wheel,
            args.site_packages.resolve(strict=True),
            args.source_root.resolve(strict=True),
        )
        matched_files = evidence["environment"]["source_wheel_install_matches"]
        require(
            all(name in matched_files for name in VISUALIZATION_FILES),
            "Required visualization module or browser asset is absent from the wheel",
        )
        evidence["visualization_package_files"] = {
            name: matched_files[name] for name in VISUALIZATION_FILES
        }
        evidence["visualization"] = check_visualization_pipeline(output)
        evidence["success"] = True
    except Exception as exc:
        evidence["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
    evidence["completed_at"] = datetime.now(timezone.utc).isoformat()
    evidence_path = output / "visualization-wheel-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "success": evidence["success"],
                "evidence": str(evidence_path),
                "error": evidence.get("error"),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if evidence["success"] else 1)


if __name__ == "__main__":
    main()
