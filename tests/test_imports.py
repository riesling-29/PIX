"""Import checks for the PIX package foundation."""

import importlib

import pix

PUBLIC_OWNER_MODULES = (
    "pix.api",
    "pix.contracts",
    "pix.compute",
    "pix.engine",
    "pix.intelligence",
    "pix.ocel",
    "pix.projection",
    "pix.results",
    "pix.models",
    "pix.viewer",
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
    "pix.ocel.build",
    "pix.ocel.canonical",
    "pix.ocel.canonical.contract",
    "pix.ocel.canonical.v1",
    "pix.ocel.ingest",
    "pix.ocel.ingest.contract",
    "pix.ocel.ingest.reader",
    "pix.ocel.ingest.formats.common",
    "pix.ocel.ingest.formats.json",
    "pix.ocel.ingest.formats.sqlite",
    "pix.ocel.ingest.formats.xml",
    "pix.ocel.metadata",
    "pix.ocel.model",
    "pix.ocel.report",
    "pix.ocel.validate",
    "pix.projection.process_state",
    "pix.contracts.analysis",
    "pix.contracts.conformance",
    "pix.contracts.discovery",
    "pix.contracts.execution",
    "pix.contracts.graph",
    "pix.contracts.models",
    "pix.contracts.replay",
    "pix.compute.context",
    "pix.compute.dfg",
    "pix.compute.ocdfg",
    "pix.compute.executions",
    "pix.compute.variants",
    "pix.compute.discovery",
    "pix.compute.model_semantics",
    "pix.compute.conformance",
    "pix.compute.replay",
    "pix.ocel.export",
)


def test_package_import_and_version() -> None:
    assert pix.__version__ == "0.4.0"


def test_public_owner_modules_import() -> None:
    imported = tuple(importlib.import_module(name) for name in PUBLIC_OWNER_MODULES)

    assert tuple(module.__name__ for module in imported) == PUBLIC_OWNER_MODULES


def test_structural_modules_import() -> None:
    imported = tuple(importlib.import_module(name) for name in STRUCTURAL_MODULES)

    assert tuple(module.__name__ for module in imported) == STRUCTURAL_MODULES
