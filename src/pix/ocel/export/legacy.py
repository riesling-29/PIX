"""OCEL 1 JSON export with explicit, opt-in losses from OCEL 2 facts."""

from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pix._publication import FilePublication, publish_bytes
from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.formats.common import ValueEncoding
from pix.ocel.ingest.formats.legacy import _migrate
from pix.ocel.model import OCEL, OCEL_EPOCH


@dataclass(frozen=True, slots=True)
class LegacyLoss:
    code: str
    message: str
    at: tuple[str, ...] = ()


class LegacyLossError(ValueError):
    def __init__(self, losses):
        self.losses = tuple(losses)
        super().__init__(
            "OCEL 1 export would lose information: "
            + ", ".join(sorted({x.code for x in losses}))
        )


@dataclass(frozen=True, slots=True)
class LegacyExport:
    publication: FilePublication
    source_digest: str
    exported_digest: str
    losses: tuple[LegacyLoss, ...]
    profile: str = "pix.ocel1-json.loss-explicit.v1"


def export_ocel1_json(
    log: OCEL, path: str | Path, *, allow_loss: bool = False, overwrite: bool = False
) -> LegacyExport:
    """Export the classic OCEL 1 shape; no enriched-extension claim is made.

    With allow_loss=True, O2O and E2O qualifiers are omitted, histories become their
    latest observed values, and datetime attributes become ISO strings. All changes
    are disclosed in the receipt. Default refusal occurs before touching output.
    """
    if not isinstance(log, OCEL):
        raise TypeError("log must be OCEL")
    if type(allow_loss) is not bool:
        raise TypeError("allow_loss must be bool")
    source = canonical_digest(log).identifier
    losses = []

    def value(v, at):
        if isinstance(v, datetime):
            losses.append(
                LegacyLoss(
                    "time_attribute_to_string",
                    "JSON OCEL 1 does not declare time attribute types",
                    at,
                )
            )
            return (
                v.astimezone(timezone.utc)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
        return v

    if log.o2o:
        losses.append(
            LegacyLoss(
                "object_relationships_omitted", f"{len(log.o2o)} O2O relations omitted"
            )
        )
    participants = defaultdict(set)
    for rel in log.e2o:
        participants[rel.event].add(rel.object)
        if rel.qualifier:
            losses.append(
                LegacyLoss(
                    "qualifier_omitted",
                    "E2O membership cannot retain qualifier",
                    (rel.event, rel.object, rel.qualifier),
                )
            )
    objects = {}
    for obj in sorted(log.objects, key=lambda o: o.id):
        assignments = defaultdict(list)
        for attr in obj.attributes:
            assignments[attr.name].append(attr)
        attributes = {}
        for name, history in sorted(assignments.items()):
            latest = max(history, key=lambda a: a.time.astimezone(timezone.utc))
            if len(history) != 1 or latest.time != OCEL_EPOCH:
                losses.append(
                    LegacyLoss(
                        "object_history_collapsed",
                        "Latest observed value exported without assignment time",
                        (obj.id, name),
                    )
                )
            attributes[name] = value(latest.value, ("object", obj.id, name))
        objects[obj.id] = {"ocel:type": obj.type, "ocel:ovmap": attributes}
    events = {}
    for event in sorted(log.events, key=lambda e: e.id):
        events[event.id] = {
            "ocel:activity": event.type,
            "ocel:timestamp": event.time.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "ocel:omap": sorted(participants[event.id]),
            "ocel:vmap": {
                a.name: value(a.value, ("event", event.id, a.name))
                for a in sorted(event.attributes, key=lambda a: a.name)
            },
        }
    document = {
        "ocel:global-log": {
            "ocel:version": "1.0",
            "ocel:ordering": "timestamp",
            "ocel:attribute-names": sorted(
                {
                    a.name
                    for kind in (*log.event_types, *log.object_types)
                    for a in kind.attributes
                }
            ),
            "ocel:object-types": sorted(t.name for t in log.object_types),
        },
        "ocel:global-event": {},
        "ocel:global-object": {},
        "ocel:objects": objects,
        "ocel:events": events,
    }
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
    ).encode("utf-8")
    restored, _ = _migrate(json.loads(payload), encoding=ValueEncoding.JSON)
    if not restored.valid:
        raise ValueError("legacy export failed semantic validation")
    exported = canonical_digest(restored.candidate).identifier

    def schema(types):
        return tuple(
            sorted(
                (t.name, tuple(sorted((a.name, a.type.value) for a in t.attributes)))
                for t in types
            )
        )

    before_schema = (schema(log.event_types), schema(log.object_types))
    after_schema = (
        schema(restored.candidate.event_types),
        schema(restored.candidate.object_types),
    )
    if before_schema != after_schema:
        losses.append(
            LegacyLoss(
                "schema_reconstructed",
                "OCEL 1 infers schemas from values; unused declarations or attribute types may differ",
            )
        )
    if exported != source and not losses:
        raise ValueError("unexplained legacy roundtrip difference")
    if losses and not allow_loss:
        raise LegacyLossError(losses)
    if Path(path).suffix.lower() == ".gz":
        payload = gzip.compress(payload, mtime=0)
    publication = publish_bytes(
        payload, path, overwrite=overwrite, prefix=".pix-ocel1-"
    )
    return LegacyExport(publication, source, exported, tuple(losses))


__all__ = ["LegacyLoss", "LegacyLossError", "LegacyExport", "export_ocel1_json"]
