"""Check the additive MODEL/W4 registry without importing calculation modules.

This establishes traceability and source identity, not semantic correctness,
reference equivalence, domain acceptance, or test execution. Run --freeze-hashes
only after the source/test snapshot is ready; --strict-hashes then detects drift.
The historical SCOPE-01 and union registries are read but never rewritten.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = "docs/requirements/models-w4-2026-09-17/implementation_registry.json"
CLAIM_STATE = "native_profiles_structurally_registered_semantic_acceptance_pending"
HASH_MEANING = (
    "Source identity only; not evidence that tests passed or semantics match."
)


def read_json(path: Path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def repository_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("paths must be nonempty repository-relative POSIX strings")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"path escapes repository: {value!r}")
    resolved = (ROOT / candidate).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
        raise ValueError(f"missing repository file: {value!r}")
    return resolved


def defined_symbol(path, symbol, cache):
    """Resolve only real definitions, including methods, at their concrete file.

    Dynamic package exports and imported aliases do not qualify. A reexport's
    implementation must instead name the concrete defining file in the registry.
    """
    if not isinstance(symbol, str) or not all(
        part.isidentifier() for part in symbol.split(".")
    ):
        return False
    if path not in cache:
        cache[path] = ast.parse(
            path.read_text(encoding="utf-8-sig"), filename=str(path)
        )
    node = cache[path]
    for part in symbol.split("."):
        definitions = [
            child
            for child in getattr(node, "body", ())
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and child.name == part
        ]
        if len(definitions) != 1:
            return False
        node = definitions[0]
    return True


def snapshot_paths(document):
    paths = {
        document["source_registry"],
        document["historical_implementation_registry"],
        document["development_plan"],
    }
    paths.update(document["shared_integration_files"])
    for packet in document["packets"]:
        paths.update(packet["code_files"])
        paths.update(packet["test_files"])
        for feature in packet["supporting_existing_features"]:
            paths.update(feature["code_files"])
            paths.update(feature["test_files"])
    return sorted(paths)


def validate(document, *, strict_hashes=False):
    errors = []
    warnings = []
    ast_cache = {}

    def require(condition, message):
        if not condition:
            errors.append(message)

    def file(value, prefix):
        try:
            return repository_path(value)
        except (ValueError, OSError) as exc:
            errors.append(f"{prefix}: {exc}")
            return None

    def strings(values, prefix, *, nonempty=True):
        valid = isinstance(values, list) and all(
            isinstance(value, str) and bool(value.strip()) for value in values
        )
        require(valid, f"{prefix}: expected a list of nonblank strings")
        if not valid:
            return []
        require(not nonempty or bool(values), f"{prefix}: must not be empty")
        require(len(values) == len(set(values)), f"{prefix}: duplicate entries")
        return values

    require(isinstance(document, dict), "registry must be an object")
    if not isinstance(document, dict):
        return errors, warnings
    require(document.get("schema_version") == "1.0", "unexpected schema_version")
    require(document.get("state") == CLAIM_STATE, "unsupported completion/claim state")
    require(
        document.get("reference_replacement_verified") is False,
        "global reference_replacement_verified must remain false",
    )
    require(
        document.get("domain_review_status") == "not_yet_reviewed",
        "global domain_review_status must remain not_yet_reviewed",
    )
    require(
        document.get("evidence_kind") == "structural_traceability_only",
        "registry evidence must be structural_traceability_only",
    )
    source = file(document.get("source_registry"), "source_registry")
    historical = file(
        document.get("historical_implementation_registry"), "historical_registry"
    )
    plan = file(document.get("development_plan"), "development_plan")
    if not source or not historical or not plan:
        return errors, warnings
    for path in strings(
        document.get("shared_integration_files"), "shared_integration_files"
    ):
        file(path, "shared_integration_files")
    try:
        source_document = read_json(source)
        source_rows = {row["id"]: row for row in source_document["rows"]}
        require(
            len(source_rows) == len(source_document["rows"]), "duplicate source row IDs"
        )
        require(
            source_document.get("scope_id") == "SCOPE-01", "unexpected source scope"
        )
        require(
            all(
                row.get("replacement_verified") is False for row in source_rows.values()
            ),
            "historical source replacement claims changed; explicit review is required",
        )
        plan_ids = set(
            re.findall(r"\b[A-Z][A-Z0-9]*-\d{2}\b", plan.read_text(encoding="utf-8"))
        )
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(f"source document: {exc}")
        return errors, warnings
    packets = document.get("packets")
    require(
        isinstance(packets, list) and bool(packets), "packets must be a nonempty list"
    )
    if not isinstance(packets, list):
        return errors, warnings
    seen = set()
    for index, packet in enumerate(packets):
        prefix = f"packet[{index}]"
        if not isinstance(packet, dict):
            errors.append(f"{prefix}: expected an object")
            continue
        identifier = packet.get("id")
        require(
            isinstance(identifier, str) and bool(identifier), f"{prefix}: missing id"
        )
        if not isinstance(identifier, str):
            continue
        prefix = identifier
        require(identifier not in seen, f"{prefix}: duplicate packet id")
        seen.add(identifier)
        require(
            packet.get("implementation_status") == "native_profile",
            f"{prefix}: unsupported completion status",
        )
        require(
            packet.get("reference_replacement_verified") is False,
            f"{prefix}: reference_replacement_verified must remain false",
        )
        require(
            packet.get("domain_review_status") == "not_yet_reviewed",
            f"{prefix}: domain_review_status must remain not_yet_reviewed",
        )
        require(
            packet.get("domain") in ("case_centric", "object_centric", "cross_model"),
            f"{prefix}: invalid domain",
        )
        for key in (
            "title",
            "exact_native_profile",
            "source_mapping_boundary",
            "withdrawal_condition",
        ):
            require(
                isinstance(packet.get(key), str) and bool(packet[key].strip()),
                f"{prefix}: {key} must describe the bounded claim",
            )
        for identifier in strings(
            packet.get("source_scope_ids"), f"{prefix}.source_scope_ids"
        ):
            require(
                identifier in source_rows, f"{prefix}: unknown source ID {identifier}"
            )
        for identifier in strings(packet.get("plan_ids"), f"{prefix}.plan_ids"):
            require(identifier in plan_ids, f"{prefix}: unknown plan ID {identifier}")
        strings(packet.get("remaining_limits"), f"{prefix}.remaining_limits")
        code_files = strings(packet.get("code_files"), f"{prefix}.code_files")
        tests = strings(packet.get("test_files"), f"{prefix}.test_files")
        for path in code_files + tests:
            file(path, prefix)
        require(
            all(
                path.startswith("src/pix/") and path.endswith(".py")
                for path in code_files
            ),
            f"{prefix}: code_files must name PIX Python implementation files",
        )
        require(
            all(path.startswith("tests/") and path.endswith(".py") for path in tests),
            f"{prefix}: test_files must name Python test files",
        )
        entrypoints = packet.get("entrypoints")
        require(
            isinstance(entrypoints, list) and bool(entrypoints),
            f"{prefix}: missing entrypoints",
        )
        entry_ids = set()
        for entry in entrypoints if isinstance(entrypoints, list) else []:
            if not isinstance(entry, dict):
                errors.append(f"{prefix}: entrypoint must be an object")
                continue
            path, symbol = entry.get("path"), entry.get("symbol")
            key = (path, symbol)
            if not all(isinstance(value, str) for value in key):
                errors.append(f"{prefix}: entrypoint path and symbol must be strings")
                continue
            require(key not in entry_ids, f"{prefix}: duplicate entrypoint {key}")
            entry_ids.add(key)
            require(
                path in code_files,
                f"{prefix}: entrypoint file absent from code_files: {path}",
            )
            concrete = file(path, prefix)
            if concrete:
                try:
                    require(
                        defined_symbol(concrete, symbol, ast_cache),
                        f"{prefix}: no concrete AST definition for {path}:{symbol}",
                    )
                except (SyntaxError, UnicodeError, OSError) as exc:
                    errors.append(f"{prefix}: {exc}")
        support = packet.get("supporting_existing_features")
        require(
            isinstance(support, list),
            f"{prefix}: supporting_existing_features must be a list",
        )
        for feature in support if isinstance(support, list) else []:
            if not isinstance(feature, dict):
                errors.append(f"{prefix}: supporting feature must be an object")
                continue
            require(
                isinstance(feature.get("meaning"), str)
                and bool(feature["meaning"].strip()),
                f"{prefix}: supporting feature needs a meaning",
            )
            for identifier in strings(
                feature.get("source_scope_ids"),
                f"{prefix}.support.source_ids",
                nonempty=False,
            ):
                require(
                    identifier in source_rows,
                    f"{prefix}: unknown supporting source ID {identifier}",
                )
            for key in ("code_files", "test_files"):
                for path in strings(feature.get(key), f"{prefix}.support.{key}"):
                    file(path, prefix)
    snapshot = document.get("source_snapshot")
    require(isinstance(snapshot, dict), "source_snapshot must be an object")
    if not isinstance(snapshot, dict) or errors:
        return errors, warnings
    require(
        snapshot.get("meaning") == HASH_MEANING,
        "source_snapshot must qualify its evidence",
    )
    hashes = snapshot.get("sha256")
    require(isinstance(hashes, dict), "source_snapshot.sha256 must be an object")
    if not isinstance(hashes, dict):
        return errors, warnings
    if snapshot.get("state") == "unfrozen":
        require(
            not hashes and snapshot.get("recorded_at") is None,
            "unfrozen snapshot must have no hashes/timestamp",
        )
        if strict_hashes:
            errors.append("source snapshot is not frozen")
        else:
            warnings.append(
                "Source hashes not frozen; run --freeze-hashes after the final source/test edits."
            )
    elif snapshot.get("state") == "frozen":
        require(
            isinstance(snapshot.get("recorded_at"), str),
            "frozen snapshot needs recorded_at",
        )
        expected = set(snapshot_paths(document))
        require(
            set(hashes) == expected,
            "hash inventory differs from registry file inventory",
        )
        for path, digest in hashes.items():
            require(
                isinstance(digest, str)
                and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                f"invalid SHA256: {path}",
            )
            concrete = file(path, "hash")
            if concrete and hashlib.sha256(concrete.read_bytes()).hexdigest() != digest:
                message = f"source hash differs: {path}"
                (errors if strict_hashes else warnings).append(message)
    else:
        errors.append("invalid source_snapshot.state")
    return errors, warnings


def self_test(document):
    """Mutation checks exercise refusal paths; these are not mining tests."""
    mutations = (
        (
            "global parity claim",
            lambda d: d.update(reference_replacement_verified=True),
        ),
        (
            "packet parity claim",
            lambda d: d["packets"][0].update(reference_replacement_verified=True),
        ),
        (
            "domain approval claim",
            lambda d: d["packets"][0].update(domain_review_status="approved"),
        ),
        (
            "duplicate packet",
            lambda d: d["packets"].append(copy.deepcopy(d["packets"][0])),
        ),
        (
            "unknown scope ID",
            lambda d: d["packets"][0].update(source_scope_ids=["NOT-A-SOURCE"]),
        ),
        ("unknown plan ID", lambda d: d["packets"][0].update(plan_ids=["NOT-A-PLAN"])),
        (
            "missing definition",
            lambda d: d["packets"][0]["entrypoints"][0].update(
                symbol="missing_registry_test_symbol"
            ),
        ),
        (
            "path traversal",
            lambda d: d["packets"][0]["code_files"].append("../outside.py"),
        ),
        ("missing limitation", lambda d: d["packets"][0].update(remaining_limits=[])),
    )
    failures = []
    for name, mutate in mutations:
        candidate = copy.deepcopy(document)
        mutate(candidate)
        if not validate(candidate)[0]:
            failures.append(f"self-test accepted {name}")
    candidate = copy.deepcopy(document)
    candidate["source_snapshot"] = {
        "state": "unfrozen",
        "recorded_at": None,
        "meaning": HASH_MEANING,
        "sha256": {},
    }
    if not validate(candidate, strict_hashes=True)[0]:
        failures.append("self-test accepted strict checking without frozen hashes")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--strict-hashes", action="store_true")
    parser.add_argument(
        "--freeze-hashes",
        action="store_true",
        help="Explicitly record current source/test hashes after structural validation",
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        path = repository_path(args.registry)
        document = read_json(path)
        errors, warnings = validate(
            document, strict_hashes=args.strict_hashes and not args.freeze_hashes
        )
        if args.self_test and not errors:
            errors.extend(self_test(document))
        if args.freeze_hashes and not errors:
            document["source_snapshot"] = {
                "state": "frozen",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "meaning": HASH_MEANING,
                "sha256": {
                    value: hashlib.sha256(
                        repository_path(value).read_bytes()
                    ).hexdigest()
                    for value in snapshot_paths(document)
                },
            }
            errors, warnings = validate(document, strict_hashes=True)
            if not errors:
                path.write_bytes(
                    (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode(
                        "utf-8"
                    )
                )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        errors, warnings = [str(exc)], []
    report = {
        "registry": args.registry,
        "valid": not errors,
        "evidence_kind": "structural_traceability_only",
        "strict_hashes": args.strict_hashes or args.freeze_hashes,
        "self_test_requested": args.self_test,
        "errors": errors,
        "warnings": warnings,
        "meaning": "Checks links, concrete AST definitions, claim boundaries and optional hashes; does not execute mining tests.",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
