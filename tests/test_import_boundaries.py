"""AST-based dependency checks for PIX layer owners."""

import ast
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "pix"
FORBIDDEN_EXTERNAL_ROOTS = {"schumpeter", "pig", "ocpx", "ocpa", "pm4py"}


def _source_files() -> tuple[Path, ...]:
    files = tuple(sorted(PACKAGE_ROOT.rglob("*.py")))

    assert files, "PIX source files were not found"
    return files


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = ("pix", *relative.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    module_name = _module_name(path)
    package_name = (
        module_name if path.name == "__init__.py" else module_name.rsplit(".", 1)[0]
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package_parts = package_name.split(".")
                retained_parts = package_parts[: len(package_parts) - node.level + 1]
                if node.module:
                    retained_parts.extend(node.module.split("."))
                relative_base = ".".join(retained_parts)
                modules.add(relative_base)
                modules.update(f"{relative_base}.{alias.name}" for alias in node.names)
            elif node.module:
                modules.add(node.module)
                modules.update(f"{node.module}.{alias.name}" for alias in node.names)

    return modules


def _imports_pix_owner(path: Path, owner: str) -> bool:
    qualified_owner = f"pix.{owner}"
    return any(
        module == qualified_owner or module.startswith(f"{qualified_owner}.")
        for module in _imported_modules(path)
    )


def test_pix_does_not_import_forbidden_projects() -> None:
    violations: list[str] = []

    for path in _source_files():
        imported_roots = {
            module.split(".", maxsplit=1)[0] for module in _imported_modules(path)
        }
        forbidden = sorted(imported_roots & FORBIDDEN_EXTERNAL_ROOTS)
        if forbidden:
            violations.append(f"{path.name}: {', '.join(forbidden)}")

    assert not violations, "Forbidden project imports: " + "; ".join(violations)


def test_contracts_imports_standard_library_only() -> None:
    contract_files = tuple(sorted((PACKAGE_ROOT / "contracts").rglob("*.py")))
    violations: list[str] = []

    assert contract_files, "PIX contract source files were not found"
    for path in contract_files:
        imported_roots = {
            module.split(".", maxsplit=1)[0] for module in _imported_modules(path)
        }
        non_standard = sorted(imported_roots - sys.stdlib_module_names)
        if non_standard:
            violations.append(f"{path.name}: {', '.join(non_standard)}")

    assert not violations, "Non-standard contract imports: " + "; ".join(violations)


def test_compute_import_boundary() -> None:
    forbidden_owners = {"intelligence", "projection", "engine", "api"}
    violations: list[str] = []

    for path in sorted((PACKAGE_ROOT / "compute").rglob("*.py")):
        imported = {
            owner for owner in forbidden_owners if _imports_pix_owner(path, owner)
        }
        if imported:
            violations.append(f"{path.name}: {', '.join(sorted(imported))}")

    assert not violations, "Compute boundary violations: " + "; ".join(violations)


def test_intelligence_import_boundary() -> None:
    forbidden_owners = {"compute", "projection", "engine", "api"}
    violations: list[str] = []

    for path in sorted((PACKAGE_ROOT / "intelligence").rglob("*.py")):
        imported = {
            owner for owner in forbidden_owners if _imports_pix_owner(path, owner)
        }
        if imported:
            violations.append(f"{path.name}: {', '.join(sorted(imported))}")

    assert not violations, "Intelligence boundary violations: " + "; ".join(violations)


def test_projection_import_boundary() -> None:
    forbidden_owners = {"compute", "intelligence"}
    violations: list[str] = []

    for path in sorted((PACKAGE_ROOT / "projection").rglob("*.py")):
        imported = {
            owner for owner in forbidden_owners if _imports_pix_owner(path, owner)
        }
        if imported:
            violations.append(f"{path.name}: {', '.join(sorted(imported))}")

    assert not violations, "Projection boundary violations: " + "; ".join(violations)
