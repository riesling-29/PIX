"""Small source-preserving case-log utilities, independent of collectors."""

from __future__ import annotations

import json
from dataclasses import dataclass

from pix.event_log.adapters import case_log_digest
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


@dataclass(frozen=True, slots=True)
class AttributeSequence:
    case_id: str
    event_ids: tuple[str, ...]
    attributes: tuple[CaseAttribute | None, ...]


@dataclass(frozen=True, slots=True)
class AttributeSequences:
    source_digest: str
    key: str
    resolve_globals: bool
    sequences: tuple[AttributeSequence, ...]


def event_attribute_sequences(
    log: CaseLog, key: str, *, resolve_globals: bool = True
) -> AttributeSequences:
    """Keep every source event and typed/nested value; missing stays None.

    The result retains CaseAttribute objects rather than coercing them into strings
    or numbers. A recorded null attribute differs from a missing attribute. These
    native facts may include nonfinite XES values and are not a numeric matrix.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(key, str):
        raise TypeError("key must be str")
    if type(resolve_globals) is not bool:
        raise TypeError("resolve_globals must be bool")
    return AttributeSequences(
        case_log_digest(log),
        key,
        resolve_globals,
        tuple(
            AttributeSequence(
                trace.id,
                tuple(e.id for e in trace.events),
                tuple(
                    log.attribute(e, key) if resolve_globals else e.attribute(key)
                    for e in trace.events
                ),
            )
            for trace in log.traces
        ),
    )


def case_log_from_activity_text(
    text: str | bytes, *, max_bytes: int = 1_000_000, max_events: int = 100_000
) -> CaseLog:
    """Read a JSON array of activity arrays for hand-authored examples.

    Each inner array is a case in explicit source order, including empty cases.
    No timestamps, object relationships or source event identities are invented.
    Internal positional IDs identify this synthetic input only. Delimiters inside
    activity labels have no special meaning.
    """
    if any(type(n) is not int or n < 1 for n in (max_bytes, max_events)):
        raise ValueError("limits must be positive integers")
    if isinstance(text, str):
        text = text.encode("utf-8")
    if not isinstance(text, bytes):
        raise TypeError("text must be UTF-8 bytes or str")
    if len(text) > max_bytes:
        raise ValueError("activity text exceeds byte limit")
    try:
        rows = json.loads(text)
    except RecursionError as error:
        raise ValueError("activity text nesting limit exceeded") from error
    if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
        raise ValueError("expected a JSON array of activity arrays")
    if sum(len(row) for row in rows) > max_events:
        raise ValueError("activity text exceeds event limit")
    if any(not isinstance(a, str) or not a.strip() for row in rows for a in row):
        raise ValueError("activities must be nonblank strings")
    return CaseLog(
        tuple(
            CaseTrace(
                f"synthetic:case:{i}",
                tuple(
                    CaseEvent(
                        f"synthetic:event:{i}:{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(row)
                ),
            )
            for i, row in enumerate(rows)
        ),
        attributes=(
            CaseAttribute("pix:source_kind", "string", "synthetic_activity_sequences"),
        ),
    )


__all__ = [
    "AttributeSequence",
    "AttributeSequences",
    "event_attribute_sequences",
    "case_log_from_activity_text",
]
