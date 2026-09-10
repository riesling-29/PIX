"""Strict OCEL 2.0 SQLite adapter using only the standard library."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from pix.ocel.build import BuildResult
from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import (
    ValueEncoding,
    map_document,
    mapping_failure,
    schema_failure,
    syntax_failure,
)

_CORE_TABLES = {
    "event",
    "object",
    "event_object",
    "object_object",
    "event_map_type",
    "object_map_type",
}
_EVENT_FIXED_COLUMNS = {"ocel_id", "ocel_time"}
_OBJECT_FIXED_COLUMNS = {"ocel_id", "ocel_time", "ocel_changed_field"}


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Read and map an OCEL 2.0 SQLite database in read-only mode."""

    connection: sqlite3.Connection | None = None
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        document = _read_document(connection)
    except sqlite3.DatabaseError as exc:
        raise syntax_failure(
            "invalid_sqlite",
            f"Invalid or unreadable SQLite database: {exc}.",
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    return map_document(document, encoding=ValueEncoding.SQLITE)


def _read_document(connection: sqlite3.Connection) -> dict[str, list[object]]:
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = sorted(_CORE_TABLES.difference(tables))
    if missing:
        raise schema_failure(
            "missing_sqlite_table",
            f"Missing required OCEL SQLite table(s): {', '.join(missing)}.",
        )

    event_maps = _read_type_map(connection, "event_map_type")
    object_maps = _read_type_map(connection, "object_map_type")
    _require_dynamic_tables(tables, "event", event_maps)
    _require_dynamic_tables(tables, "object", object_maps)

    event_types = _read_type_declarations(connection, kind="event", mappings=event_maps)
    object_types = _read_type_declarations(
        connection, kind="object", mappings=object_maps
    )
    e2o = _read_e2o(connection)
    o2o = _read_o2o(connection)
    events = _read_events(connection, event_maps, e2o)
    objects = _read_objects(connection, object_maps, o2o)
    _require_relation_sources(e2o, events, "event_object", "event")
    _require_relation_sources(o2o, objects, "object_object", "object")
    return {
        "eventTypes": event_types,
        "objectTypes": object_types,
        "events": events,
        "objects": objects,
    }


def _require_relation_sources(
    relationships: dict[str, list[dict[str, object]]],
    records: list[dict[str, object]],
    table: str,
    kind: str,
) -> None:
    sources = {record["id"] for record in records}
    for source in relationships:
        if source not in sources:
            raise mapping_failure(
                "missing_sqlite_relation_source",
                f"Table '{table}' references absent {kind} source '{source}'.",
                (table, str(source)),
            )


def _read_type_map(
    connection: sqlite3.Connection,
    table: str,
) -> dict[str, str]:
    columns = _columns(connection, table)
    if "ocel_type" not in columns:
        raise schema_failure(
            "missing_sqlite_column",
            f"Table '{table}' is missing column 'ocel_type'.",
            (table,),
        )
    mapped_column = next(
        (name for name in ("ocel_type_map", "ocel_type_corr") if name in columns),
        None,
    )
    if mapped_column is None:
        raise schema_failure(
            "missing_sqlite_column",
            f"Table '{table}' has no supported physical type-name column.",
            (table,),
        )

    result: dict[str, str] = {}
    query = (
        f"SELECT {_quote('ocel_type')}, {_quote(mapped_column)} FROM {_quote(table)}"
    )
    for row in connection.execute(query):
        logical = row["ocel_type"]
        physical = row[mapped_column]
        if not isinstance(logical, str) or not logical.strip():
            raise mapping_failure(
                "invalid_sqlite_type_name",
                f"Table '{table}' contains an invalid logical type name.",
                (table,),
            )
        if not isinstance(physical, str) or not physical.strip():
            raise mapping_failure(
                "invalid_sqlite_type_mapping",
                f"Type '{logical}' has an invalid physical mapping.",
                (table, logical),
            )
        existing = result.get(logical)
        if existing is not None and existing != physical:
            raise mapping_failure(
                "ambiguous_sqlite_type_mapping",
                f"Type '{logical}' maps to multiple physical names.",
                (table, logical),
            )
        result[logical] = physical
    return result


def _require_dynamic_tables(
    tables: set[str],
    kind: str,
    mappings: dict[str, str],
) -> None:
    missing = sorted(
        f"{kind}_{physical}"
        for physical in mappings.values()
        if f"{kind}_{physical}" not in tables
    )
    if missing:
        raise schema_failure(
            "missing_sqlite_type_table",
            f"Missing mapped {kind} table(s): {', '.join(missing)}.",
        )


def _read_type_declarations(
    connection: sqlite3.Connection,
    *,
    kind: str,
    mappings: dict[str, str],
) -> list[dict[str, object]]:
    fixed = _EVENT_FIXED_COLUMNS if kind == "event" else _OBJECT_FIXED_COLUMNS
    declarations: list[dict[str, object]] = []
    for logical, physical in mappings.items():
        table = f"{kind}_{physical}"
        columns = _columns(connection, table)
        missing = sorted(fixed.difference(columns))
        if missing:
            raise schema_failure(
                "missing_sqlite_column",
                f"Table '{table}' is missing column(s): {', '.join(missing)}.",
                (table,),
            )
        attributes = []
        for name, declared_type in columns.items():
            if name in fixed:
                continue
            attributes.append(
                {"name": name, "type": _map_sql_type(declared_type, table, name)}
            )
        declarations.append({"name": logical, "attributes": attributes})
    return declarations


def _read_events(
    connection: sqlite3.Connection,
    mappings: dict[str, str],
    relationships: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    _require_columns(connection, "event", {"ocel_id", "ocel_type"})
    events: list[dict[str, object]] = []
    for root in connection.execute(
        "SELECT ocel_id, ocel_type FROM event ORDER BY rowid"
    ):
        event_id = root["ocel_id"]
        event_type = root["ocel_type"]
        physical = mappings.get(event_type)
        if physical is None:
            raise mapping_failure(
                "unmapped_event_type",
                f"Event '{event_id}' references unmapped type '{event_type}'.",
                ("event", str(event_id)),
            )
        table = f"event_{physical}"
        rows = connection.execute(
            f"SELECT * FROM {_quote(table)} WHERE ocel_id = ?",
            (event_id,),
        ).fetchall()
        if len(rows) != 1:
            raise mapping_failure(
                "ambiguous_event_record",
                f"Event '{event_id}' has {len(rows)} rows in '{table}'.",
                (table, str(event_id)),
            )
        row = rows[0]
        attributes = [
            {"name": name, "value": row[name]}
            for name in row.keys()
            if name not in _EVENT_FIXED_COLUMNS and row[name] is not None
        ]
        events.append(
            {
                "id": event_id,
                "type": event_type,
                "time": row["ocel_time"],
                "attributes": attributes,
                "relationships": relationships.get(event_id, []),
            }
        )
    return events


def _read_objects(
    connection: sqlite3.Connection,
    mappings: dict[str, str],
    relationships: dict[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    _require_columns(connection, "object", {"ocel_id", "ocel_type"})
    objects: list[dict[str, object]] = []
    for root in connection.execute(
        "SELECT ocel_id, ocel_type FROM object ORDER BY rowid"
    ):
        object_id = root["ocel_id"]
        object_type = root["ocel_type"]
        physical = mappings.get(object_type)
        if physical is None:
            raise mapping_failure(
                "unmapped_object_type",
                f"Object '{object_id}' references unmapped type '{object_type}'.",
                ("object", str(object_id)),
            )
        table = f"object_{physical}"
        rows = connection.execute(
            f"SELECT * FROM {_quote(table)} WHERE ocel_id = ? ORDER BY ocel_time",
            (object_id,),
        ).fetchall()
        if not rows:
            raise mapping_failure(
                "missing_object_record",
                f"Object '{object_id}' has no rows in '{table}'.",
                (table, str(object_id)),
            )
        attributes: list[dict[str, object]] = []
        for row in rows:
            changed = row["ocel_changed_field"]
            if changed is not None and changed not in row.keys():
                raise mapping_failure(
                    "unknown_changed_field",
                    f"Object '{object_id}' changes unknown field '{changed}'.",
                    (table, str(object_id)),
                )
            names = (
                [changed]
                if changed is not None
                else [name for name in row.keys() if name not in _OBJECT_FIXED_COLUMNS]
            )
            for name in names:
                if row[name] is None:
                    continue
                attributes.append(
                    {
                        "name": name,
                        "value": row[name],
                        "time": row["ocel_time"],
                    }
                )
        objects.append(
            {
                "id": object_id,
                "type": object_type,
                "attributes": attributes,
                "relationships": relationships.get(object_id, []),
            }
        )
    return objects


def _read_e2o(
    connection: sqlite3.Connection,
) -> dict[str, list[dict[str, object]]]:
    _require_columns(
        connection,
        "event_object",
        {"ocel_event_id", "ocel_object_id", "ocel_qualifier"},
    )
    result: dict[str, list[dict[str, object]]] = {}
    query = (
        "SELECT ocel_event_id, ocel_object_id, ocel_qualifier "
        "FROM event_object ORDER BY rowid"
    )
    for row in connection.execute(query):
        result.setdefault(row["ocel_event_id"], []).append(
            {
                "objectId": row["ocel_object_id"],
                "qualifier": row["ocel_qualifier"],
            }
        )
    return result


def _read_o2o(
    connection: sqlite3.Connection,
) -> dict[str, list[dict[str, object]]]:
    _require_columns(
        connection,
        "object_object",
        {"ocel_source_id", "ocel_target_id", "ocel_qualifier"},
    )
    result: dict[str, list[dict[str, object]]] = {}
    query = (
        "SELECT ocel_source_id, ocel_target_id, ocel_qualifier "
        "FROM object_object ORDER BY rowid"
    )
    for row in connection.execute(query):
        result.setdefault(row["ocel_source_id"], []).append(
            {
                "objectId": row["ocel_target_id"],
                "qualifier": row["ocel_qualifier"],
            }
        )
    return result


def _columns(connection: sqlite3.Connection, table: str) -> dict[str, str]:
    rows = connection.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    if not rows:
        raise schema_failure(
            "missing_sqlite_table",
            f"Missing SQLite table '{table}'.",
            (table,),
        )
    return {row["name"]: row["type"] for row in rows}


def _require_columns(
    connection: sqlite3.Connection,
    table: str,
    required: set[str],
) -> None:
    missing = sorted(required.difference(_columns(connection, table)))
    if missing:
        raise schema_failure(
            "missing_sqlite_column",
            f"Table '{table}' is missing column(s): {', '.join(missing)}.",
            (table,),
        )


def _map_sql_type(declared: Any, table: str, column: str) -> str:
    normalized = str(declared).strip().upper()
    if any(token in normalized for token in ("CHAR", "CLOB", "TEXT")):
        return "string"
    if any(token in normalized for token in ("DATE", "TIME")):
        return "time"
    if "BOOL" in normalized:
        return "boolean"
    if "INT" in normalized:
        return "integer"
    if any(token in normalized for token in ("REAL", "FLOA", "DOUB")):
        return "float"
    raise schema_failure(
        "unsupported_sqlite_attribute_type",
        f"Column '{table}.{column}' has unsupported type '{declared}'.",
        (table, column),
    )


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


__all__ = ["load"]
