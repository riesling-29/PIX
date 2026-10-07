"""Local consumer policy example, not a Hub or a PIX approval algorithm.

Versioned artifact IDs prevent a v1 test from being treated as v2 evidence.
Persist original import evidence separately from canonical calculation identity.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    project_object_cases,
)
from pix.object_centric.temporal_summary import temporal_summary
from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    import_ocel,
)
from pix.ocel.export import export_ocel
from pix.results import result_document

T = datetime(2026, 9, 20, tzinfo=timezone.utc)


def run_example(directory: Path, *, version2_bytes: bytes = b"changed artifact"):
    directory.mkdir(parents=True, exist_ok=True)
    namespace = "local-review/artifacts"
    hashes = tuple(
        sha256(b).hexdigest() for b in (b"original artifact", version2_bytes)
    )
    log = OCEL(
        event_types=tuple(EventType(x) for x in ("Created", "TestPassed", "Modified")),
        object_types=(
            ObjectType(
                "Artifact",
                (
                    Attribute("version", ValueType.STRING),
                    Attribute("sha256", ValueType.STRING),
                ),
            ),
        ),
        objects=tuple(
            Object(
                f"artifact@v{i + 1}",
                "Artifact",
                (
                    ObjectAttr("version", f"v{i + 1}", T),
                    ObjectAttr("sha256", digest, T),
                ),
            )
            for i, digest in enumerate(hashes)
        ),
        events=(
            Event("create-v1", "Created", T),
            Event("test-v1", "TestPassed", T + timedelta(seconds=1)),
            Event("modify-v2", "Modified", T + timedelta(seconds=2)),
        ),
        e2o=(
            E2O("create-v1", "artifact@v1", "output"),
            E2O("test-v1", "artifact@v1", "subject"),
            E2O("modify-v2", "artifact@v2", "output"),
        ),
    )
    source = directory / "source.jsonocel"
    export_ocel(log, source, format="ocel20-json")
    imported = import_ocel(source)
    canonical = imported.require_ocel(reject_timezone_assumptions=True)
    projection = project_object_cases(canonical, ObjectCaseProjectionSpec("Artifact"))
    summary = temporal_summary(canonical)
    # Consumer selection only. This is not a new mining or decision operator.
    artifacts = []
    for trace in projection.case_log.traces:
        evidence = tuple(
            e.attribute("pix:source_event_id").value
            for e in trace.events
            if e.attribute("concept:name").value == "TestPassed"
        )
        artifacts.append(
            {
                "namespace": namespace,
                "objectId": trace.id,
                "version": trace.id.split("@")[1],
                "sha256": hashes[0 if trace.id.endswith("v1") else 1],
                "testEventIds": evidence,
                "testPassed": True if evidence else None,
            }
        )
    output = {
        "exampleProfile": "pix.local-versioned-artifact-review.v1",
        "namespace": namespace,
        "snapshot": imported.source_sha256,
        "observation": {
            "cutoff": (T + timedelta(seconds=2)).isoformat(),
            "closed": False,
            "meaning": "all supplied events observed; future tests unknown",
        },
        "input": imported.describe(),
        "projection": projection.describe(),
        "calculation": result_document(summary),
        "artifacts": artifacts,
        "policy": "Test evidence must reference the exact version; deployment and retry belong to the consumer.",
    }
    (directory / "consumer-review.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(
        json.dumps(
            run_example(parser.parse_args().output), ensure_ascii=False, indent=2
        )
    )
