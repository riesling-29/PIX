"""Inventory exported OCPM/facade functions and methods; never infer semantics.

Run from a checkout using its development interpreter. The explicit namespace
scope is an audit denominator, not a claim to enumerate every PIX operation.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def inventory() -> list[dict]:
    oc = importlib.import_module("pix.object_centric")
    # _MODULES is the lazy namespace's own advertised list, not a filesystem scan.
    namespaces = [
        "pix.api",
        "pix.object_centric",
        *("pix.object_centric." + name for name in oc._MODULES),
        "pix.case_centric.context_ngrams",
    ]
    rows = {}

    def record(function, alias, kind):
        if not function.__module__.startswith("pix."):
            return
        key = function.__module__ + "." + function.__qualname__
        if key not in rows:
            path = Path(inspect.getsourcefile(function)).resolve()
            parameters = inspect.signature(function).parameters
            rows[key] = {
                "symbol": key,
                "kind": kind,
                "export_paths": [],
                "source_path": path.relative_to(ROOT).as_posix(),
                "source_line": inspect.getsourcelines(function)[1],
                "parameters": ", ".join(parameters),
                "return_annotation": str(inspect.signature(function).return_annotation),
                "semantic_review": "not_reviewed",
                "review_row": "",
            }
        rows[key]["export_paths"].append(alias)

    for namespace in namespaces:
        module = importlib.import_module(namespace)
        exports = getattr(module, "__all__", None)
        if exports is None:
            exports = sorted(
                name
                for name, value in vars(module).items()
                if not name.startswith("_")
                and (inspect.isfunction(value) or inspect.isclass(value))
                and value.__module__ == namespace
            )
        for name in exports:
            value = getattr(module, name)
            alias = namespace + "." + name
            if inspect.isfunction(value):
                record(value, alias, "function")
            elif inspect.isclass(value) and value.__module__.startswith("pix."):
                # Include methods defined on exported classes; inherited/dunder
                # methods and dataclass fields are explicitly outside this list.
                for method_name, raw in vars(value).items():
                    if method_name.startswith("_"):
                        continue
                    method = (
                        raw.__func__
                        if isinstance(raw, (staticmethod, classmethod))
                        else raw
                    )
                    if inspect.isfunction(method):
                        record(method, alias + "." + method_name, "method")
    for row in rows.values():
        row["export_paths"] = "; ".join(sorted(set(row["export_paths"])))
    return [rows[key] for key in sorted(rows)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    args = parser.parse_args()
    reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
    rows = inventory()
    unknown = set(reviews) - {row["symbol"] for row in rows}
    if unknown:
        raise ValueError(f"Review map names unexported symbols: {sorted(unknown)}")
    for row in rows:
        if row["symbol"] in reviews:
            row["semantic_review"] = "definition_checked_not_replacement_verified"
            row["review_row"] = reviews[row["symbol"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "symbols": len(rows),
                "functions": sum(row["kind"] == "function" for row in rows),
                "methods": sum(row["kind"] == "method" for row in rows),
                "definition_checked": len(reviews),
                "not_reviewed": len(rows) - len(reviews),
            }
        )
    )


if __name__ == "__main__":
    main()
