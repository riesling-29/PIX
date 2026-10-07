"""Check the native mining implementation inventory without running algorithms.

File/function presence is structural evidence only. This script cannot certify
mathematical equivalence, test success, an optional runtime, or completeness.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/requirements/union-2026-09-15/implementation_registry.json"


def _entrypoint_exists(entrypoint: str) -> bool:
    parts = entrypoint.split(".")
    for split in range(len(parts) - 1, 0, -1):
        candidate = ROOT / "src" / Path(*parts[:split]).with_suffix(".py")
        if not candidate.is_file():
            continue
        tree = ast.parse(candidate.read_text(encoding="utf-8"))
        names = parts[split:]
        for name in names:
            nodes = [
                node
                for node in tree.body
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
                and node.name == name
            ]
            if not nodes:
                return False
            tree = nodes[0]
        return True
    return False


def check(path: Path, *, strict_hashes: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    baseline_path = ROOT / data["source_registry"]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = {row["id"] for row in baseline["rows"]}
    rows = data["rows"]
    exclusions = data["excluded_rows"]
    packages = data["work_packages"]
    errors = []
    stale = []
    unavailable_local_reports = []
    allowed = {
        "native_profile",
        "partial",
        "unimplemented",
        "external_runtime_unverified",
    }
    all_ids = [row["source_id"] for row in rows + exclusions]
    duplicates = sorted(k for k, count in Counter(all_ids).items() if count != 1)
    if duplicates:
        errors.append({"duplicate_ids": duplicates})
    if set(all_ids) != expected:
        errors.append(
            {
                "missing_ids": sorted(expected - set(all_ids)),
                "extra_ids": sorted(set(all_ids) - expected),
            }
        )
    if (
        hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        != data["source_registry_sha256"]
    ):
        errors.append({"baseline_hash_changed": str(baseline_path.relative_to(ROOT))})
    package_ids = {package["id"] for package in packages}
    if len(package_ids) != len(packages):
        errors.append({"duplicate_package_ids": True})
    row_packages = {row["source_id"]: row["work_package"] for row in rows}
    package_members = [rid for package in packages for rid in package["source_ids"]]
    if Counter(package_members) != Counter(row_packages.keys()):
        errors.append({"package_membership_does_not_partition_rows": True})
    for package in packages:
        for rid in package["source_ids"]:
            if row_packages.get(rid) != package["id"]:
                errors.append({"id": rid, "wrong_package_membership": package["id"]})
        for dependency in package["dependencies"]:
            if dependency not in package_ids:
                errors.append(
                    {"package": package["id"], "missing_dependency": dependency}
                )
    actual_counts = {
        "source_rows": len(expected),
        "calculation_and_support_rows": len(rows),
        "excluded_rows": len(exclusions),
        "work_packages": len(packages),
        "work_packages_by_domain": dict(
            Counter(package["domain"] for package in packages)
        ),
        "rows_by_domain": dict(Counter(row["domain"] for row in rows)),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "reference_replacement_verified_rows": sum(
            row["reference_replacement_verified"] for row in rows
        ),
    }
    if data["counts"] != actual_counts:
        errors.append(
            {"stale_recorded_counts": data["counts"], "actual_counts": actual_counts}
        )
    for row in rows:
        rid = row["source_id"]
        if row["work_package"] not in package_ids:
            errors.append({"id": rid, "unknown_package": row["work_package"]})
        if row["status"] not in allowed:
            errors.append({"id": rid, "invalid_status": row["status"]})
        if not row["residual_variant_gaps"]:
            errors.append(
                {"id": rid, "missing_explicit_residual_or_parity_statement": True}
            )
        if (
            row["status"] in {"native_profile", "external_runtime_unverified"}
            and not row["actual"]["entrypoints"]
        ):
            errors.append({"id": rid, "status_without_entrypoint": True})
        if row["reference_replacement_verified"]:
            errors.append({"id": rid, "unsupported_parity_upgrade": True})
        for symbol in row["actual"]["entrypoints"]:
            if not _entrypoint_exists(symbol):
                errors.append({"id": rid, "missing_entrypoint": symbol})
        for value in row["actual"]["sources"] + row["actual"]["tests"]:
            if not (ROOT / value).is_file():
                errors.append({"id": rid, "missing_source_or_test": value})
        for report in row["evidence"]["recorded_reports"]:
            if not (ROOT / report).is_file():
                if report.startswith(".artifacts/"):
                    unavailable_local_reports.append(report)
                else:
                    errors.append({"id": rid, "missing_recorded_report": report})
    for record in data["file_snapshot"]:
        candidate = ROOT / record["path"]
        if not candidate.is_file():
            errors.append({"missing_snapshot_file": record["path"]})
        elif hashlib.sha256(candidate.read_bytes()).hexdigest() != record["sha256"]:
            stale.append(record["path"])
    if strict_hashes and stale:
        errors.append({"source_or_test_changed_since_snapshot": stale})
    return {
        "registry": str(path.relative_to(ROOT)),
        "source_rows": len(expected),
        "calculation_and_support_rows": len(rows),
        "excluded_rows": len(exclusions),
        "work_packages": len(packages),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "errors": errors,
        "changed_since_snapshot": stale,
        "unavailable_local_reports": sorted(set(unavailable_local_reports)),
        "runtime_algorithms_executed": False,
        "meaning": "Structural inventory validation only; counts are not algorithm completion percentages.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT)
    parser.add_argument("--strict-hashes", action="store_true")
    args = parser.parse_args()
    result = check(args.registry.resolve(), strict_hashes=args.strict_hashes)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(result["errors"])


if __name__ == "__main__":
    raise SystemExit(main())
