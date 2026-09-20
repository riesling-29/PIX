"""Classic UTF-8 .dfg frequency exchange, independently implemented in PIX.

Format: activity count and labels; start/end section sizes and index x count
rows; then source > target x count rows until EOF. It cannot store case counts,
empty traces, event witnesses, performance, or original activity frequencies.
No missing boundaries or case statistics are inferred from graph topology.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pix._publication import publish_bytes
from pix.contracts.result import ComputationResult, ComputeStatus
from pix.model_io.common import ParsedModel, fail


@dataclass(frozen=True, slots=True)
class DFGFile:
    activities: tuple[str, ...]
    edges: tuple[tuple[str, str, int], ...]
    start_counts: tuple[tuple[str, int], ...]
    end_counts: tuple[tuple[str, int], ...]

    def __post_init__(self):
        if (
            not isinstance(self.activities, tuple)
            or any(
                not isinstance(a, str)
                or not a
                or a != a.strip()
                or any(c in a for c in "\r\n")
                for a in self.activities
            )
            or len(set(self.activities)) != len(self.activities)
        ):
            raise ValueError(
                "DFG labels must be unique, nonblank single lines without surrounding whitespace"
            )
        known = set(self.activities)
        for rows, width in (
            (self.edges, 3),
            (self.start_counts, 2),
            (self.end_counts, 2),
        ):
            if not isinstance(rows, tuple) or any(
                not isinstance(r, tuple) or len(r) != width for r in rows
            ):
                raise TypeError("invalid DFG frequency rows")
            if any(
                any(a not in known for a in r[:-1])
                or type(r[-1]) is not int
                or r[-1] <= 0
                for r in rows
            ):
                raise ValueError(
                    "DFG frequencies require known labels and positive integer counts"
                )
            if len({r[:-1] for r in rows}) != len(rows):
                raise ValueError("duplicate DFG frequency coordinate")


@dataclass(frozen=True, slots=True)
class DFGExchangeProjection:
    model: DFGFile
    omitted_information: tuple[str, ...]
    source_computation_id: str


def project_dfg_exchange(result: ComputationResult) -> DFGExchangeProjection:
    """Explicitly drop non-format information; caller retains this loss receipt."""
    from pix.case_centric.discovery import CaseRelationGraph, RelationDiscoverySpec

    if not isinstance(result, ComputationResult) or not isinstance(
        result.value, CaseRelationGraph
    ):
        raise TypeError("expected a case DFG calculation result")
    if (
        result.operator_id != "pix.case_centric.discover_dfg"
        or result.status is not ComputeStatus.COMPUTED
        or not result.value.complete
        or not isinstance(result.spec, RelationDiscoverySpec)
        or result.spec.counting != "occurrences"
    ):
        raise ValueError("classic DFG export requires complete occurrence frequencies")
    g = result.value
    model = DFGFile(
        tuple(a for a, _ in g.activity_counts),
        tuple((e.source, e.target, e.count) for e in g.edges),
        g.start_counts,
        g.end_counts,
    )
    return DFGExchangeProjection(
        model,
        (
            "activity_occurrence_counts",
            "edge_case_counts",
            "trace_count",
            "empty_trace_count",
            "examined_event_pairs",
            "computation_provenance",
        ),
        result.computation_id,
    )


def dumps_dfg(model: DFGFile | ParsedModel) -> bytes:
    if isinstance(model, ParsedModel):
        model = model.model
    if not isinstance(model, DFGFile):
        raise TypeError("model must be DFGFile; project calculation results explicitly")
    indices = {a: i for i, a in enumerate(model.activities)}
    rows = [str(len(model.activities)), *model.activities]
    for boundary in (model.start_counts, model.end_counts):
        rows.append(str(len(boundary)))
        rows.extend(f"{indices[a]}x{n}" for a, n in sorted(boundary))
    rows.extend(f"{indices[a]}>{indices[b]}x{n}" for a, b, n in sorted(model.edges))
    return ("\n".join(rows) + "\n").encode("utf-8")


def loads_dfg(data: str | bytes, *, max_bytes: int = 16 * 1024 * 1024) -> ParsedModel:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, bytes):
        raise TypeError("DFG input must be bytes or text")
    if len(data) > max_bytes:
        fail("dfg", "byte limit exceeded", code="resource_limit")
    try:
        rows = data.decode("utf-8-sig").replace("\r\n", "\n").split("\n")
        if rows[-1] == "":
            rows.pop()
        pos = 0

        def line():
            nonlocal pos
            if pos == len(rows):
                raise ValueError("truncated DFG section")
            value = rows[pos]
            pos += 1
            return value

        def number(text):
            if not re.fullmatch(r"[0-9]{1,1000}", text):
                raise ValueError("DFG requires nonnegative decimal integers")
            return int(text)

        size = number(line())
        if size > len(rows) - pos:
            raise ValueError("truncated activity list")
        activities = tuple(line() for _ in range(size))

        def label(text):
            index = number(text)
            if index >= len(activities):
                raise ValueError("DFG index outside activity list")
            return activities[index]

        boundaries = []
        for _ in range(2):
            count = number(line())
            if count > len(rows) - pos:
                raise ValueError("truncated boundary list")
            boundary = []
            for _ in range(count):
                a, n = line().split("x")
                boundary.append((label(a), number(n)))
            boundaries.append(tuple(sorted(boundary)))
        edges = []
        while pos < len(rows):
            pair, n = line().split("x")
            a, b = pair.split(">")
            edges.append((label(a), label(b), number(n)))
        model = DFGFile(activities, tuple(sorted(edges)), *boundaries)
    except (ValueError, UnicodeError) as error:
        fail("dfg", str(error), code="invalid_dfg")
    return ParsedModel(
        model, "dfg", "classic-frequency", "classic", sha256(data).hexdigest()
    )


def read_dfg(path: str | Path, *, max_bytes: int = 16 * 1024 * 1024) -> ParsedModel:
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    with Path(path).open("rb") as stream:
        return loads_dfg(stream.read(max_bytes + 1), max_bytes=max_bytes)


def write_dfg(model, path: str | Path, *, overwrite: bool = False):
    return publish_bytes(
        dumps_dfg(model), path, overwrite=overwrite, prefix=".pix-dfg-"
    )


__all__ = [
    "DFGFile",
    "DFGExchangeProjection",
    "project_dfg_exchange",
    "dumps_dfg",
    "loads_dfg",
    "read_dfg",
    "write_dfg",
]
