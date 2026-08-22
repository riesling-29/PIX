"""PIX OCEL canonical byte representation, version 1.

Canonical V1 is an internal identity representation. It is not an OCEL 2.0
interchange serialization and must not be used as one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pix.ocel.build import build
from pix.ocel.canonical.contract import CanonicalizationError
from pix.ocel.model import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    Value,
)


def _canonical_time(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_value(value: Value) -> dict[str, object]:
    if isinstance(value, datetime):
        return {
            "type": "time",
            "value": _canonical_time(value),
        }

    # bool must be checked before int because bool is a subclass of int.
    if isinstance(value, bool):
        return {
            "type": "boolean",
            "value": value,
        }

    if isinstance(value, int):
        return {
            "type": "integer",
            "value": str(value),
        }

    if isinstance(value, float):
        return {
            "type": "float",
            "value": value.hex(),
        }

    if isinstance(value, str):
        return {
            "type": "string",
            "value": value,
        }

    # model.py prevents unsupported canonical values from reaching this point.
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _canonicalize(ocel: OCEL) -> OCEL:
    result = build(
        event_types=ocel.event_types,
        object_types=ocel.object_types,
        events=ocel.events,
        objects=ocel.objects,
        e2o=ocel.e2o,
        o2o=ocel.o2o,
    )

    if not result.valid:
        raise CanonicalizationError(result.report)

    canonical = result.ocel
    if canonical is None:  # pragma: no cover - guarded by BuildResult.valid
        raise RuntimeError("valid build did not expose canonical OCEL")

    return canonical


def _attribute(attribute: Attribute) -> dict[str, object]:
    return {
        "name": attribute.name,
        "type": attribute.type.value,
    }


def _event_type(event_type: EventType) -> dict[str, object]:
    return {
        "name": event_type.name,
        "attributes": [_attribute(value) for value in event_type.attributes],
    }


def _object_type(object_type: ObjectType) -> dict[str, object]:
    return {
        "name": object_type.name,
        "attributes": [_attribute(value) for value in object_type.attributes],
    }


def _event_attribute(attribute: EventAttr) -> dict[str, object]:
    return {
        "name": attribute.name,
        "value": _canonical_value(attribute.value),
    }


def _object_attribute(attribute: ObjectAttr) -> dict[str, object]:
    return {
        "name": attribute.name,
        "time": _canonical_time(attribute.time),
        "value": _canonical_value(attribute.value),
    }


def _event(event: Event) -> dict[str, object]:
    return {
        "id": event.id,
        "type": event.type,
        "time": _canonical_time(event.time),
        "attributes": [_event_attribute(value) for value in event.attributes],
    }


def _object(obj: Object) -> dict[str, object]:
    return {
        "id": obj.id,
        "type": obj.type,
        "attributes": [_object_attribute(value) for value in obj.attributes],
    }


def _e2o(relation: E2O) -> dict[str, object]:
    return {
        "event": relation.event,
        "object": relation.object,
        "qualifier": relation.qualifier,
    }


def _o2o(relation: O2O) -> dict[str, object]:
    return {
        "source": relation.source,
        "target": relation.target,
        "qualifier": relation.qualifier,
    }


def serialize_v1(ocel: OCEL) -> bytes:
    """Return deterministic Canonical V1 bytes for a semantically valid OCEL."""

    if not isinstance(ocel, OCEL):
        raise TypeError("ocel must be OCEL")

    canonical = _canonicalize(ocel)
    payload = {
        "format": "pix.ocel.canonical",
        "version": 1,
        "eventTypes": [_event_type(value) for value in canonical.event_types],
        "objectTypes": [_object_type(value) for value in canonical.object_types],
        "events": [_event(value) for value in canonical.events],
        "objects": [_object(value) for value in canonical.objects],
        "e2o": [_e2o(value) for value in canonical.e2o],
        "o2o": [_o2o(value) for value in canonical.o2o],
    }

    text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return text.encode("utf-8")


__all__ = ["serialize_v1"]
