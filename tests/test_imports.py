"""Import checks for the PIX package foundation."""

import importlib

import pix

PUBLIC_OWNER_MODULES = (
    "pix.api",
    "pix.contracts",
    "pix.compute",
    "pix.engine",
    "pix.intelligence",
    "pix.projection",
)

STRUCTURAL_MODULES = (
    "pix.contracts.constraint",
    "pix.contracts.dataset",
    "pix.contracts.event",
    "pix.contracts.object",
    "pix.contracts.relation",
    "pix.contracts.result",
    "pix.compute.integrity",
    "pix.compute.lifecycle",
    "pix.compute.lineage",
    "pix.compute.object_projection",
    "pix.compute.recovery",
    "pix.compute.temporal",
    "pix.compute.trace",
    "pix.intelligence.diagnostics",
    "pix.intelligence.findings",
    "pix.intelligence.recommendations",
    "pix.intelligence.rules",
    "pix.projection.process_state",
)


def test_package_import_and_version() -> None:
    assert pix.__version__ == "0.1.0"


def test_public_owner_modules_import() -> None:
    imported = tuple(importlib.import_module(name) for name in PUBLIC_OWNER_MODULES)

    assert tuple(module.__name__ for module in imported) == PUBLIC_OWNER_MODULES


def test_structural_modules_import() -> None:
    imported = tuple(importlib.import_module(name) for name in STRUCTURAL_MODULES)

    assert tuple(module.__name__ for module in imported) == STRUCTURAL_MODULES
