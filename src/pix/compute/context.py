"""Validated immutable canonical input and shared indexes for native operators."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from pix.ocel import (
    E2O,
    OCEL,
    Event,
    Issue,
    Object,
    Report,
    build,
    canonical_digest,
    validate,
)


class InvalidOCELInput(ValueError):
    """Context construction failed; the original semantic report is retained."""

    def __init__(self, report: Report) -> None:
        super().__init__("Cannot prepare computation context for invalid OCEL")
        self.report = report


@dataclass(frozen=True, slots=True, init=False)
class ComputationContext:
    """Validated immutable input and indexes, reusable across native operators.

    Construction is the only supported way to create a context. Index dictionaries
    are private snapshots wrapped in read-only proxies, with immutable values.
    Datetimes are normalized by PIX's existing builder before ordering: no floating
    Unix timestamp conversion is used. A context has no mutable analysis cache.
    """

    log: OCEL
    source_digest: str
    events_by_id: Mapping[str, Event]
    objects_by_id: Mapping[str, Object]
    e2o_by_event: Mapping[str, tuple[E2O, ...]]
    objects_by_type: Mapping[str, tuple[Object, ...]]
    e2o_by_object: Mapping[str, tuple[E2O, ...]]

    def __init__(self, log: OCEL) -> None:
        if not isinstance(log, OCEL):
            raise TypeError("log must be OCEL")
        report = validate(log)
        if not report.valid:
            raise InvalidOCELInput(report)
        try:
            built = build(
                event_types=log.event_types,
                object_types=log.object_types,
                events=log.events,
                objects=log.objects,
                e2o=log.e2o,
                o2o=log.o2o,
            )
            normalized = built.ocel
            if normalized is None:
                raise InvalidOCELInput(built.report)
            normalized = replace(normalized, import_info=log.import_info)
            digest = canonical_digest(normalized).identifier
        except (OverflowError, TypeError, ValueError) as exc:
            if isinstance(exc, InvalidOCELInput):
                raise
            raise InvalidOCELInput(
                Report(
                    (
                        Issue(
                            code="unrepresentable_canonical_input",
                            message=f"Cannot normalize canonical input: {exc}",
                        ),
                    )
                )
            ) from exc

        objects: dict[str, list[Object]] = {
            item.name: [] for item in normalized.object_types
        }
        relations: dict[str, list[E2O]] = {obj.id: [] for obj in normalized.objects}
        for obj in normalized.objects:
            objects[obj.type].append(obj)
        for relation in normalized.e2o:
            relations[relation.object].append(relation)

        by_event: dict[str, list[E2O]] = {event.id: [] for event in normalized.events}
        for relation in normalized.e2o:
            by_event[relation.event].append(relation)
        object.__setattr__(
            self,
            "objects_by_id",
            MappingProxyType({obj.id: obj for obj in normalized.objects}),
        )
        object.__setattr__(
            self,
            "e2o_by_event",
            MappingProxyType({key: tuple(values) for key, values in by_event.items()}),
        )
        object.__setattr__(self, "log", normalized)
        object.__setattr__(self, "source_digest", digest)
        object.__setattr__(
            self,
            "events_by_id",
            MappingProxyType({event.id: event for event in normalized.events}),
        )
        object.__setattr__(
            self,
            "objects_by_type",
            MappingProxyType({name: tuple(values) for name, values in objects.items()}),
        )
        object.__setattr__(
            self,
            "e2o_by_object",
            MappingProxyType(
                {object_id: tuple(values) for object_id, values in relations.items()}
            ),
        )

    @classmethod
    def build(cls, log: OCEL) -> ComputationContext:
        return cls(log)


__all__ = ("ComputationContext", "InvalidOCELInput")
