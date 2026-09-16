"""Check SCOPE-01 traceability without importing reference packages.

Default: validate committed identifiers, document links, and PIX source evidence.
--reference-root: additionally hash the previously extracted official wheels.
This does not test algorithms or establish semantic replacement equivalence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "docs/requirements/scope-01"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(reference_root: Path | None = None) -> dict:
    registry = read_json(SCOPE / "replacement_registry.json")
    catalog = read_json(SCOPE / "reference_catalog.json")
    plan = ROOT / "docs/requirements/2026-09-13_PIX_DETAILED_DEVELOPMENT_PLAN.md"
    tasks = set(re.findall(r"\| ([A-Z]+-\d{2}) \|", plan.read_text(encoding="utf-8")))
    rows = registry["rows"]
    errors: list[dict] = []

    def require(condition, kind, detail):
        if not condition:
            errors.append({"kind": kind, "detail": detail})

    declarations = {(d["path"], d["symbol"]) for p in catalog["packages"] for d in p["referenced_declarations"]}
    symbols: set[tuple[str, str]] = set()
    variants: set[tuple[str, str, str]] = set()
    source_paths = {f["path"] for p in catalog["packages"] for f in p["files"]}
    for row in rows:
        rid = row["id"]
        for key in ("question", "input", "output", "remaining", "area", "library", "reference_version"):
            require(isinstance(row.get(key), str) and bool(row[key].strip()), "required_field", [rid, key])
        require(row["implementation"] in registry["status_definitions"], "implementation", rid)
        require(row["semantics"] in registry["semantic_definitions"], "semantics", rid)
        require(row["replacement_verified"] is False, "unreviewed_replacement_claim", rid)
        require(bool(row["next_tasks"]), "missing_task", rid)
        for task in row["next_tasks"]:
            require(task in tasks, "unknown_task", [rid, task])
        for path in row["pix_sources"]:
            require((ROOT / path).is_file(), "pix_source_missing", [rid, path])
        for evidence in row["evidence_ids"]:
            require(evidence in registry["evidence_register"], "unknown_evidence", [rid, evidence])
        for ref in row["reference_symbols"]:
            key = (ref["path"], ref["symbol"])
            symbols.add(key)
            require(key in declarations, "reference_declaration_missing", [rid, *key])
        for variant in row["reference_variants"]:
            require(variant["path"] in source_paths, "variant_file_missing", [rid, variant["path"]])
            for member in variant["members"]:
                variants.add((variant["path"], variant["selector"], str(member)))
        if row["implementation"] == "absent":
            require(not row["pix_apis"] and not row["evidence_ids"], "absent_has_implementation_evidence", rid)
        else:
            require(bool(row["pix_sources"]), "implementation_source_required", rid)

    require(len(rows) == len({r["id"] for r in rows}), "duplicate_ids", len(rows))
    coverage = []
    reference_hashes = 0
    for package in catalog["packages"]:
        require(not package["parse_errors"], "reference_parse_errors", package["package"])
        facades = [f for f in package["functions"] if f["facade"] and f["public_name"]]
        entries = [f for f in package["functions"] if f["entry_module"] and f["public_name"]]
        missing_functions = [f for f in facades + entries if (f["path"], f["symbol"]) not in symbols]
        missing_members = []
        for selector in package["selectors"]:
            for member in selector["members"]:
                keys = [(selector["path"], selector["selector"], str(member.get(k, ""))) for k in ("name", "key_expression")]
                if not any(key in variants for key in keys):
                    missing_members.append([selector["path"], selector["selector"], member["name"]])
        missing_dynamic = [d for d in package["dynamic_variant_assignments"] if (d["path"], d["selector"], d["member"]) not in variants]
        require(not missing_functions, "unmapped_function", missing_functions)
        require(not missing_members, "unmapped_selector_member", missing_members)
        require(not missing_dynamic, "unmapped_dynamic_variant", missing_dynamic)
        if reference_root is not None:
            wheel_root = reference_root / f"{package['package']}-{package['version']}-wheel"
            for source in package["files"]:
                path = wheel_root / source["path"]
                same = path.is_file() and sha256(path) == source["sha256"]
                require(same, "reference_source_hash", source["path"])
                reference_hashes += int(same)
        coverage.append({
            "package": package["package"], "python_files": len(package["files"]),
            "public_facade_definitions": len(facades), "public_entry_module_definitions": len(entries),
            "selector_registries": len(package["selectors"]),
            "selector_members": sum(len(s["members"]) for s in package["selectors"]),
            "dynamic_variant_assignments": len(package["dynamic_variant_assignments"]),
            "unmapped_functions": len(missing_functions), "unmapped_selector_members": len(missing_members),
            "unmapped_dynamic_variants": len(missing_dynamic),
        })

    pix_hashes = 0
    for file in registry["pix_source_evidence"]["files"]:
        path = ROOT / file["path"]
        same = path.is_file() and sha256(path) == file["recorded_sha256"]
        require(same, "pix_evidence_hash_changed", file["path"])
        pix_hashes += int(same)
    for evidence in registry["evidence_register"].values():
        require((ROOT / evidence["path"]).is_file(), "evidence_document_missing", evidence["path"])

    docs = {ROOT / r["appendix"] for r in rows}
    docs.add(ROOT / "docs/requirements/2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md")
    link_count = 0
    for doc in sorted(docs):
        text = doc.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", text):
            if target.startswith(("https://", "http://")):
                continue
            file_part, _, anchor = target.partition("#")
            dest = (doc.parent / file_part).resolve() if file_part else doc
            # The result file is created only after this check completes.
            exists = dest.is_file() or dest == (SCOPE / "validation.json").resolve()
            require(exists, "document_link_missing", [str(doc.relative_to(ROOT)), target])
            if anchor and exists and dest.suffix == ".md":
                headings = re.findall(r"^#{1,6} (.+)$", dest.read_text(encoding="utf-8"), re.MULTILINE)
                anchors = {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}
                require(anchor in anchors, "document_anchor_missing", [str(doc.relative_to(ROOT)), target])
            link_count += 1
    for row in rows:
        text = (ROOT / row["appendix"]).read_text(encoding="utf-8")
        require(text.count("\n## " + row["id"] + "\n") == 1, "appendix_row_missing_or_duplicate", row["id"])

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(), "passed": not errors,
        "method": "Static source identifiers/hashes and document traceability; no upstream imports or algorithm execution",
        "rows": len(rows), "implementation_counts": dict(Counter(r["implementation"] for r in rows)),
        "plan_task_ids": len(tasks), "reference_coverage": coverage,
        "reference_source_hashes_rechecked": reference_hashes,
        "reference_source_hash_check_requested": reference_root is not None,
        "pix_runtime_hashes_matched": pix_hashes,
        "pix_runtime_hashes_total": len(registry["pix_source_evidence"]["files"]),
        "local_document_links_checked": link_count,
        "registry_sha256": sha256(SCOPE / "replacement_registry.json"),
        "reference_catalog_sha256": sha256(SCOPE / "reference_catalog.json"),
        "upstream_algorithms_executed": False, "new_product_algorithm_tests_run": False,
        "scope_limitation": "Coverage closes the enumerated facade/algorithm-factory-evaluator and selector surfaces; arbitrary helpers, dynamic runtime APIs and semantic equivalence are not exhaustively certified.",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check(args.reference_root)
    if args.output is not None:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
