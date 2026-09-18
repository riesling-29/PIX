"""Standard model exchange with explicit, fail-closed supported profiles.

``read_*``/``loads_*`` return :class:`ParsedModel`: use its ``.model`` in native
calculations. ``write_*`` publishes atomically and refuses existing paths unless
``overwrite=True``. Writers accept native models or their imported wrappers.
No importer discovers a replacement model or guesses missing acceptance data.

PNML: one weighted ordinary P/T net, explicit final marking, ProM silent flag.
PTML: activity/tau, sequence/XOR/parallel and binary loops (tau-exit compatible).
BPMN 2.0: one plain start/end, atomic tasks, directed XOR/AND gateways and flows.
These profiles do not represent complete standard or upstream-library coverage.
"""

from __future__ import annotations

import os
from pathlib import Path

from pix._publication import FilePublication, publish_bytes

from .bpmn import dumps_bpmn, loads_bpmn
from .common import ModelIOError, ParsedModel, XMLLimits, fail
from .pnml import dumps_pnml, loads_pnml
from .ptml import dumps_ptml, loads_ptml


def _read(path, loader, format, limits):
    if not isinstance(limits, XMLLimits):
        raise TypeError("limits must be XMLLimits")
    with Path(path).open("rb") as stream:
        payload = stream.read(limits.max_bytes + 1)
    if len(payload) > limits.max_bytes:
        fail(format, "XML byte limit exceeded", code="resource_limit")
    return loader(payload, limits=limits)


def read_pnml(
    path: str | os.PathLike[str], *, limits: XMLLimits = XMLLimits()
) -> ParsedModel:
    return _read(path, loads_pnml, "pnml", limits)


def read_ptml(
    path: str | os.PathLike[str], *, limits: XMLLimits = XMLLimits()
) -> ParsedModel:
    return _read(path, loads_ptml, "ptml", limits)


def read_bpmn(
    path: str | os.PathLike[str], *, limits: XMLLimits = XMLLimits()
) -> ParsedModel:
    return _read(path, loads_bpmn, "bpmn", limits)


def write_pnml(
    model, path: str | os.PathLike[str], *, overwrite: bool = False
) -> FilePublication:
    return publish_bytes(
        dumps_pnml(model), path, overwrite=overwrite, prefix=".pix-pnml-"
    )


def write_ptml(
    model, path: str | os.PathLike[str], *, overwrite: bool = False
) -> FilePublication:
    return publish_bytes(
        dumps_ptml(model), path, overwrite=overwrite, prefix=".pix-ptml-"
    )


def write_bpmn(
    model, path: str | os.PathLike[str], *, overwrite: bool = False
) -> FilePublication:
    return publish_bytes(
        dumps_bpmn(model), path, overwrite=overwrite, prefix=".pix-bpmn-"
    )


__all__ = (
    "ModelIOError",
    "ParsedModel",
    "XMLLimits",
    "loads_pnml",
    "dumps_pnml",
    "read_pnml",
    "write_pnml",
    "loads_ptml",
    "dumps_ptml",
    "read_ptml",
    "write_ptml",
    "loads_bpmn",
    "dumps_bpmn",
    "read_bpmn",
    "write_bpmn",
)
