"""Stage A: independent OCEL preservation and atomic publication checks."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    OCEL_EPOCH,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    canonical_digest,
    import_ocel,
)
from pix.ocel.export import ExportError, ExportIssue, ExportResult, export_ocel
from pix.ocel.export import writer as io

UTC = timezone.utc
T = datetime(2026, 9, 9, 12, 34, 56, 123456, tzinfo=timezone(timedelta(hours=9)))
ATTRS = (
    Attribute("note", ValueType.STRING),
    Attribute("count", ValueType.INTEGER),
    Attribute("cost", ValueType.FLOAT),
    Attribute("flag", ValueType.BOOLEAN),
    Attribute("when", ValueType.TIME),
    Attribute("optional", ValueType.STRING),
)
VALUES = {"note": "", "count": 2**63 - 1, "cost": 3.25, "flag": False, "when": T}


def rich_log() -> OCEL:
    return OCEL(
        event_types=(
            EventType("Submit", ATTRS),
            EventType("unused event", (Attribute("x", ValueType.STRING),)),
        ),
        object_types=(
            ObjectType("Case", ATTRS),
            ObjectType("unused object", (Attribute("y", ValueType.BOOLEAN),)),
        ),
        events=(
            Event("e1", "Submit", T, tuple(EventAttr(k, v) for k, v in VALUES.items())),
            Event("isolated event", "Submit", T + timedelta(seconds=1)),
        ),
        objects=(
            Object(
                "o1",
                "Case",
                tuple(ObjectAttr(k, v, OCEL_EPOCH) for k, v in VALUES.items())
                + (
                    ObjectAttr("note", "changed", T),
                    ObjectAttr("count", -(2**63), T),
                    ObjectAttr(
                        "note", "same value still explicit", T + timedelta(seconds=1)
                    ),
                    ObjectAttr(
                        "note", "same value still explicit", T + timedelta(seconds=2)
                    ),
                ),
            ),
            Object(
                "o2", "Case", (ObjectAttr("note", "first assignment is not epoch", T),)
            ),
            Object("isolated object", "Case"),
        ),
        e2o=(E2O("e1", "o1", "input"), E2O("e1", "o1", "output"), E2O("e1", "o2", "")),
        o2o=(
            O2O("o1", "o2", "parent"),
            O2O("o1", "o2", "owner"),
            O2O("o2", "o1", "child"),
        ),
    )


class ExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def assert_rich_semantics(self, log: OCEL) -> None:
        self.assertEqual({e.id for e in log.events}, {"e1", "isolated event"})
        self.assertEqual(
            {obj.id for obj in log.objects}, {"o1", "o2", "isolated object"}
        )
        self.assertEqual({t.name for t in log.event_types}, {"Submit", "unused event"})
        self.assertEqual({t.name for t in log.object_types}, {"Case", "unused object"})
        self.assertEqual(
            {r.qualifier for r in log.e2o if r.object == "o1"}, {"input", "output"}
        )
        self.assertEqual(
            {(r.source, r.target, r.qualifier) for r in log.o2o},
            {
                ("o1", "o2", "parent"),
                ("o1", "o2", "owner"),
                ("o2", "o1", "child"),
            },
        )
        event = log.get_event("e1")
        values = {a.name: a.value for a in event.attributes}
        self.assertEqual(values, VALUES)
        self.assertIs(type(values["count"]), int)
        self.assertIs(type(values["flag"]), bool)
        self.assertIs(type(values["cost"]), float)
        self.assertEqual(
            event.time, datetime(2026, 9, 9, 3, 34, 56, 123456, tzinfo=UTC)
        )
        history = {(a.name, a.time): a.value for a in log.get_object("o1").attributes}
        self.assertEqual(len(history), 9)
        self.assertEqual(history["count", T], -(2**63))
        self.assertEqual(history["note", T], "changed")
        self.assertEqual(
            history["note", T + timedelta(seconds=1)], "same value still explicit"
        )
        self.assertEqual(
            history["note", T + timedelta(seconds=2)], "same value still explicit"
        )
        self.assertEqual(
            log.get_object("o2").attributes,
            (ObjectAttr("note", "first assignment is not epoch", T),),
        )
        self.assertEqual(log.get_object("isolated object").attributes, ())

    def test_all_formats_preserve_semantics_and_evidence(self) -> None:
        for fmt, suffix in (
            ("json", "json"),
            ("xml", "xml"),
            ("sqlite", "sqlite"),
            ("json", "json.gz"),
            ("xml", "xml.gz"),
        ):
            with self.subTest(format=fmt):
                path = self.directory / f"log.{suffix}"
                source = rich_log()
                result = export_ocel(source, path, format=fmt)
                restored = import_ocel(path, format=fmt).require_ocel()
                self.assert_rich_semantics(restored)
                self.assertEqual(
                    result.source_canonical_digest, canonical_digest(source)
                )
                self.assertEqual(
                    result.roundtrip_canonical_digest, result.source_canonical_digest
                )
                self.assertEqual(
                    result.output_sha256, hashlib.sha256(path.read_bytes()).hexdigest()
                )
                self.assertEqual(result.output_size, path.stat().st_size)
                self.assertEqual(result.reference_schema, "not_run")
                self.assertEqual(result.pix_semantic, "passed")
                self.assertEqual(
                    result.encoding, "gzip" if suffix.endswith(".gz") else "identity"
                )
                self.assertEqual(result.status, "published")
                with self.assertRaises(FrozenInstanceError):
                    result.profile = "different"  # type: ignore[misc]

    def test_empty_log_and_unused_schema_are_preserved(self) -> None:
        schema_only = OCEL(
            event_types=(EventType("empty", ATTRS),),
            object_types=(ObjectType("empty", ATTRS),),
        )
        for fmt in ("json", "xml", "sqlite"):
            for index, log in enumerate((OCEL(), schema_only)):
                with self.subTest(format=fmt, schema=index):
                    path = self.directory / f"empty-{index}.{fmt}"
                    export_ocel(log, path, format=fmt)
                    restored = import_ocel(path, format=fmt).require_ocel()
                    self.assertEqual(restored.events, ())
                    self.assertEqual(restored.objects, ())
                    self.assertEqual(canonical_digest(restored), canonical_digest(log))

    def test_json_is_interchange_not_canonical_bytes(self) -> None:
        path = self.directory / "log.json"
        export_ocel(rich_log(), path, format="json")
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(document), {"eventTypes", "objectTypes", "events", "objects"}
        )
        event = next(e for e in document["events"] if e["id"] == "e1")
        values = {a["name"]: a["value"] for a in event["attributes"]}
        self.assertIs(type(values["count"]), int)
        self.assertIs(type(values["flag"]), bool)
        self.assertEqual(values["when"], "2026-09-09T03:34:56.123456Z")
        self.assertEqual(len(event["relationships"]), 3)

    def test_json_retains_negative_zero_and_large_integer(self) -> None:
        source = OCEL(
            event_types=(
                EventType(
                    "E",
                    (
                        Attribute("f", ValueType.FLOAT),
                        Attribute("i", ValueType.INTEGER),
                    ),
                ),
            ),
            events=(Event("e", "E", T, (EventAttr("f", -0.0), EventAttr("i", 2**80))),),
        )
        path = self.directory / "special.json"
        export_ocel(source, path, format="json")
        restored = import_ocel(path).require_ocel()
        values = {a.name: a.value for a in restored.events[0].attributes}
        self.assertEqual(math.copysign(1.0, values["f"]), -1.0)
        self.assertEqual(values["i"], 2**80)

    def test_serialization_is_independent_of_input_order(self) -> None:
        source = rich_log()
        permuted = replace(
            source,
            events=source.events[::-1],
            objects=source.objects[::-1],
            e2o=source.e2o[::-1],
            o2o=source.o2o[::-1],
            event_types=source.event_types[::-1],
        )
        first, second = self.directory / "a.json", self.directory / "b.json"
        export_ocel(source, first, format="json")
        export_ocel(permuted, second, format="json")
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_sqlite_type_mapping_avoids_physical_collisions(self) -> None:
        source = OCEL(
            event_types=tuple(EventType(n) for n in ("map_type", "A", "a", 'x"y')),
            object_types=tuple(ObjectType(n) for n in ("object", "A", "a")),
        )
        path = self.directory / "names.sqlite"
        export_ocel(source, path, format="sqlite")
        with closing(sqlite3.connect(path)) as connection:
            rows = connection.execute(
                "SELECT ocel_type, ocel_type_map FROM event_map_type ORDER BY ocel_type"
            ).fetchall()
        self.assertEqual({name for name, _ in rows}, {"map_type", "A", "a", 'x"y'})
        self.assertEqual(len({physical.lower() for _, physical in rows}), 4)
        self.assertEqual(
            [physical for _, physical in rows], [f"t{i:08d}" for i in range(4)]
        )

    def test_sqlite_rejects_reserved_and_case_colliding_columns(self) -> None:
        for attributes in (
            (Attribute("ocel_time", ValueType.STRING),),
            (Attribute("OCEL_ID", ValueType.STRING),),
            (Attribute("a", ValueType.STRING), Attribute("A", ValueType.STRING)),
            (Attribute("nul\x00name", ValueType.STRING),),
        ):
            with self.subTest(attributes=attributes):
                path = self.directory / "invalid.sqlite"
                source = OCEL(event_types=(EventType("e", attributes),))
                with self.assertRaises(ExportError) as raised:
                    export_ocel(source, path, format="sqlite")
                self.assertEqual(raised.exception.code, "unrepresentable")
                self.assertEqual(
                    raised.exception.issues[0].code, "sqlite_column_collision"
                )
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_sqlite_refuses_unrepresentable_numbers(self) -> None:
        for value, typ, code in (
            (2**63, ValueType.INTEGER, "sqlite_int64_range"),
            (-(2**63) - 1, ValueType.INTEGER, "sqlite_int64_range"),
            (-0.0, ValueType.FLOAT, "sqlite_negative_zero"),
        ):
            with self.subTest(value=value):
                source = OCEL(
                    event_types=(EventType("E", (Attribute("x", typ),)),),
                    events=(Event("e", "E", T, (EventAttr("x", value),)),),
                )
                with self.assertRaises(ExportError) as raised:
                    export_ocel(
                        source, self.directory / "numbers.sqlite", format="sqlite"
                    )
                self.assertEqual(raised.exception.issues[0].code, code)
                self.assertIsNotNone(raised.exception.source_canonical_digest)
                self.assertEqual(list(self.directory.iterdir()), [])

    def test_existing_file_needs_explicit_overwrite(self) -> None:
        path = self.directory / "keep.json"
        path.write_bytes(b"existing contents")
        with self.assertRaises(ExportError) as raised:
            export_ocel(OCEL(), path, format="json")
        self.assertEqual(raised.exception.code, "destination_exists")
        self.assertEqual(path.read_bytes(), b"existing contents")
        export_ocel(OCEL(), path, format="json", overwrite=True)
        self.assertEqual(import_ocel(path).require_ocel(), OCEL())

    def test_semantic_failure_cannot_replace_existing_file(self) -> None:
        path = self.directory / "keep.json"
        path.write_bytes(b"existing contents")
        invalid = OCEL(events=(Event("e", "undeclared", T),))
        with self.assertRaises(ExportError) as raised:
            export_ocel(invalid, path, format="json", overwrite=True)
        self.assertEqual(raised.exception.code, "semantic_invalid")
        self.assertFalse(raised.exception.semantic_report.valid)
        self.assertEqual(path.read_bytes(), b"existing contents")
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_utc_normalization_overflow_cannot_replace_existing_file(self) -> None:
        path = self.directory / "keep.json"
        path.write_bytes(b"existing contents")
        beyond_utc_range = datetime.max.replace(tzinfo=timezone(timedelta(hours=-1)))
        source = OCEL(
            event_types=(EventType("E"),), events=(Event("e", "E", beyond_utc_range),)
        )
        with self.assertRaises(ExportError) as raised:
            export_ocel(source, path, format="json", overwrite=True)
        self.assertEqual(raised.exception.code, "normalization_failed")
        self.assertIsInstance(raised.exception.__cause__, OverflowError)
        self.assertIsNone(raised.exception.source_canonical_digest)
        self.assertEqual(path.read_bytes(), b"existing contents")
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_competing_destination_created_during_export_survives(self) -> None:
        path = self.directory / "race.json"
        real_writer = io._write_json

        def competing_writer(log: OCEL, stage: Path) -> None:
            real_writer(log, stage)
            path.write_bytes(b"competing writer owns this file")

        with patch.object(io, "_write_json", side_effect=competing_writer):
            with self.assertRaises(ExportError) as raised:
                export_ocel(OCEL(), path, format="json")
        self.assertEqual(raised.exception.code, "destination_exists")
        self.assertEqual(path.read_bytes(), b"competing writer owns this file")
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_roundtrip_mismatch_blocks_publication(self) -> None:
        path = self.directory / "bad.json"
        real_writer = io._write_json
        with patch.object(
            io, "_write_json", side_effect=lambda log, stage: real_writer(OCEL(), stage)
        ):
            with self.assertRaises(ExportError) as raised:
                export_ocel(rich_log(), path, format="json")
        self.assertEqual(raised.exception.code, "roundtrip_failed")
        self.assertTrue(raised.exception.import_result.valid)
        self.assertNotEqual(
            raised.exception.import_result.canonical_digest,
            raised.exception.source_canonical_digest,
        )
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_sqlite_serialization_failure_cleans_own_temporary(self) -> None:
        def failed_writer(log: OCEL, stage: Path) -> None:
            stage.write_bytes(b"partial database")
            raise sqlite3.OperationalError("simulated write failure")

        with patch.object(io, "_write_sqlite", side_effect=failed_writer):
            with self.assertRaises(ExportError) as raised:
                export_ocel(OCEL(), self.directory / "bad.sqlite", format="sqlite")
        self.assertEqual(raised.exception.code, "serialize_failed")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_canonicalization_failure_preserves_diagnostic_and_no_file(self) -> None:
        source = OCEL(object_types=(ObjectType("unpaired-surrogate-\ud800"),))
        with self.assertRaises(ExportError) as raised:
            export_ocel(source, self.directory / "bad.json", format="json")
        self.assertEqual(raised.exception.code, "canonicalization_failed")
        self.assertTrue(raised.exception.semantic_report.valid)
        self.assertIsNone(raised.exception.source_canonical_digest)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_unsupported_formats_and_sqlite_gzip_never_publish(self) -> None:
        for fmt in ("csv", "ocel21-parquet"):
            with self.assertRaises(ExportError) as raised:
                export_ocel(OCEL(), self.directory / "output", format=fmt)
            self.assertEqual(raised.exception.code, "unsupported_format")
        with self.assertRaises(ExportError) as raised:
            export_ocel(OCEL(), self.directory / "log.sqlite.gz", format="sqlite")
        self.assertEqual(raised.exception.code, "unsupported_encoding")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_xml_uses_explicit_no_namespace_relobj_profile(self) -> None:
        path = self.directory / "dialect.xml"
        result = export_ocel(rich_log(), path, format="ocel20-xml")
        root = ET.parse(path).getroot()
        self.assertEqual(root.tag, "log")
        self.assertEqual(
            [element.tag for element in root],
            ["object-types", "event-types", "objects", "events"],
        )
        self.assertEqual(len(root.findall("./events/event/objects/relobj")), 3)
        self.assertEqual(len(root.findall("./objects/object/objects/relobj")), 3)
        self.assertEqual(root.findall(".//relationship"), [])
        self.assertEqual(result.profile, "pix.ocel20-xml.no-namespace.relobj.v1")
        self.assertEqual(result.reference_schema, "not_run")

    def test_xml_and_gzip_preserve_whitespace_escaping_and_unicode_everywhere(
        self,
    ) -> None:
        text = 'a\rb\r\nc\nd\te <&> "한글😀"'
        typ, attr, event_id, object_id = (
            f"{prefix} {text}" for prefix in ("type", "attr", "event", "object")
        )
        source = OCEL(
            event_types=(EventType(typ, (Attribute(attr, ValueType.STRING),)),),
            object_types=(ObjectType(typ, (Attribute(attr, ValueType.STRING),)),),
            events=(Event(event_id, typ, T, (EventAttr(attr, text),)),),
            objects=(Object(object_id, typ, (ObjectAttr(attr, text, T),)),),
            e2o=(E2O(event_id, object_id, text),),
            o2o=(O2O(object_id, object_id, text),),
        )
        for suffix in ("xml", "xml.gz", "json", "json.gz", "sqlite"):
            path = self.directory / f"escaped.{suffix}"
            export_ocel(source, path, format=suffix.split(".")[0])
            restored = import_ocel(path).require_ocel()
            self.assertEqual(canonical_digest(restored), canonical_digest(source))
            self.assertEqual(restored.events[0].attributes[0].value, text)
            self.assertEqual(restored.e2o[0].qualifier, text)

    def test_xml_rejects_forbidden_chars_across_schema_records_and_relations(
        self,
    ) -> None:
        base = OCEL(
            event_types=(EventType("E", (Attribute("a", ValueType.STRING),)),),
            object_types=(ObjectType("O"),),
            events=(Event("e", "E", T, (EventAttr("a", "valid"),)),),
            objects=(Object("o", "O"),),
            e2o=(E2O("e", "o", "q"),),
        )
        for forbidden in ("\x00", "\x01", "\ufffe", "\uffff"):
            cases = (
                replace(
                    base,
                    event_types=base.event_types + (EventType("unused" + forbidden),),
                ),
                replace(
                    base,
                    object_types=(
                        ObjectType(
                            "O", (Attribute("unused" + forbidden, ValueType.STRING),)
                        ),
                    ),
                ),
                replace(
                    base, events=(Event("e", "E", T, (EventAttr("a", forbidden),)),)
                ),
                replace(base, e2o=(E2O("e", "o", forbidden),)),
                replace(base, o2o=(O2O("o", "o", forbidden),)),
                replace(base, events=(Event("e" + forbidden, "E", T),), e2o=()),
                replace(base, objects=(Object("o" + forbidden, "O"),), e2o=()),
            )
            for source in cases:
                with self.subTest(character=repr(forbidden), source=source):
                    path = self.directory / "forbidden.xml"
                    path.write_bytes(b"keep")
                    with self.assertRaises(ExportError) as raised:
                        export_ocel(source, path, format="xml", overwrite=True)
                    self.assertEqual(raised.exception.code, "unrepresentable")
                    self.assertTrue(
                        all(
                            i.code == "xml_invalid_character"
                            for i in raised.exception.issues
                        )
                    )
                    self.assertEqual(path.read_bytes(), b"keep")
                    path.unlink()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_json_sqlite_preserve_text_xml_cannot_represent(self) -> None:
        source = OCEL(
            event_types=(EventType("E", (Attribute("s", ValueType.STRING),)),),
            events=(Event("e", "E", T, (EventAttr("s", "\x00\x01\uffff"),)),),
        )
        for fmt in ("json", "sqlite"):
            path = self.directory / f"text.{fmt}"
            export_ocel(source, path, format=fmt)
            self.assertEqual(
                canonical_digest(import_ocel(path).require_ocel()),
                canonical_digest(source),
            )

    def test_xml_retains_negative_zero_and_large_integer(self) -> None:
        source = OCEL(
            event_types=(
                EventType(
                    "E",
                    (
                        Attribute("f", ValueType.FLOAT),
                        Attribute("i", ValueType.INTEGER),
                    ),
                ),
            ),
            events=(Event("e", "E", T, (EventAttr("f", -0.0), EventAttr("i", 2**80))),),
        )
        for suffix in ("xml", "xml.gz"):
            path = self.directory / f"numbers.{suffix}"
            export_ocel(source, path, format="xml")
            restored = import_ocel(path).require_ocel()
            self.assertEqual(canonical_digest(restored), canonical_digest(source))

    def test_history_before_epoch_and_epoch_assignment_survive_all_formats(
        self,
    ) -> None:
        source = OCEL(
            object_types=(ObjectType("O", (Attribute("a", ValueType.STRING),)),),
            objects=(
                Object(
                    "o",
                    "O",
                    (
                        ObjectAttr(
                            "a", "before", OCEL_EPOCH - timedelta(microseconds=1)
                        ),
                        ObjectAttr("a", "", OCEL_EPOCH),
                        ObjectAttr(
                            "a", "after", OCEL_EPOCH + timedelta(microseconds=1)
                        ),
                    ),
                ),
            ),
        )
        for fmt in ("json", "xml", "sqlite"):
            path = self.directory / f"history.{fmt}"
            export_ocel(source, path, format=fmt)
            self.assertEqual(
                canonical_digest(import_ocel(path).require_ocel()),
                canonical_digest(source),
            )

    def test_gzip_bytes_are_deterministic_without_filename_or_wall_clock_header(
        self,
    ) -> None:
        for fmt in ("json", "xml"):
            first = self.directory / f"first.{fmt}.gz"
            second = self.directory / f"second.{fmt}.gz"
            plain = self.directory / f"plain.{fmt}"
            for path in (first, second, plain):
                export_ocel(rich_log(), path, format=fmt)
            payload = first.read_bytes()
            self.assertEqual(payload, second.read_bytes())
            self.assertEqual(payload[4:8], b"\x00\x00\x00\x00")
            self.assertEqual(payload[3] & 8, 0)
            self.assertEqual(gzip.decompress(payload), plain.read_bytes())

    def test_import_provenance_does_not_enter_export_semantics(self) -> None:
        for fmt in ("json", "xml", "sqlite"):
            first, second = self.directory / f"a.{fmt}", self.directory / f"b.{fmt}"
            initial = export_ocel(rich_log(), first, format=fmt)
            imported = import_ocel(first).require_ocel()
            self.assertIsNotNone(imported.import_info)
            exported = export_ocel(imported, second, format=fmt)
            self.assertEqual(
                initial.source_canonical_digest, exported.source_canonical_digest
            )
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_invalid_serialized_artifact_cannot_replace_destination(self) -> None:
        path = self.directory / "keep.xml"
        path.write_bytes(b"keep")
        with patch.object(
            io, "_write_xml", side_effect=lambda log, stage: stage.write_bytes(b"<log>")
        ):
            with self.assertRaises(ExportError) as raised:
                export_ocel(rich_log(), path, format="xml", overwrite=True)
        self.assertEqual(raised.exception.code, "roundtrip_failed")
        self.assertFalse(raised.exception.import_result.valid)
        self.assertEqual(path.read_bytes(), b"keep")
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_publish_failure_cleans_staging_and_keeps_destination(self) -> None:
        path = self.directory / "keep.json.gz"
        path.write_bytes(b"keep")
        with patch.object(
            io, "_publish", side_effect=PermissionError("simulated denied publish")
        ):
            with self.assertRaises(ExportError) as raised:
                export_ocel(rich_log(), path, format="json", overwrite=True)
        self.assertEqual(raised.exception.code, "publish_failed")
        self.assertEqual(path.read_bytes(), b"keep")
        self.assertEqual(list(self.directory.iterdir()), [path])

    def test_cleanup_failure_does_not_hide_a_committed_artifact(self) -> None:
        path = self.directory / "published.json"
        original_unlink = Path.unlink

        def publish_with_remaining_hardlink(
            stage: Path, destination: Path, *, overwrite: bool
        ) -> Path:
            os.link(stage, destination)
            return stage

        def fail_own_temporary_unlink(candidate: Path, *args, **kwargs) -> None:
            if candidate.name.startswith(".pix-export-"):
                raise PermissionError("simulated temporary cleanup failure")
            original_unlink(candidate, *args, **kwargs)

        with (
            patch.object(io, "_publish", side_effect=publish_with_remaining_hardlink),
            patch.object(Path, "unlink", new=fail_own_temporary_unlink),
        ):
            result = export_ocel(OCEL(), path, format="json")
        self.assertEqual(result.status, "published")
        self.assertEqual(result.cleanup_issues[0].code, "temporary_cleanup_failed")
        self.assertEqual(import_ocel(path).require_ocel(), OCEL())
        leftover = Path(result.cleanup_issues[0].at[0])
        self.assertTrue(leftover.exists())
        leftover.unlink()

    def test_cleanup_failure_preserves_primary_error_and_exposes_temporary_path(
        self,
    ) -> None:
        with (
            patch.object(
                io, "_write_json", side_effect=OSError("primary write failure")
            ),
            patch.object(Path, "unlink", side_effect=PermissionError("cleanup denied")),
        ):
            with self.assertRaises(ExportError) as raised:
                export_ocel(OCEL(), self.directory / "absent.json", format="json")
        error = raised.exception
        self.assertEqual(error.code, "serialize_failed")
        self.assertIn("primary write failure", str(error))
        self.assertEqual(error.cleanup_issues[0].code, "temporary_cleanup_failed")
        Path(error.cleanup_issues[0].at[0]).unlink()

    def test_public_argument_and_result_contracts(self) -> None:
        for log, path, options in (
            (None, "x", {}),
            (OCEL(), b"bytes", {}),
            (OCEL(), "", {}),
            (OCEL(), "x", {"overwrite": 1}),
        ):
            with self.assertRaises(TypeError):
                export_ocel(log, path, format="json", **options)
        digest = canonical_digest(OCEL())
        result = ExportResult(
            "x",
            "ocel20-json",
            "pix.ocel20-json.native-primitives.v1",
            digest,
            "0" * 64,
            0,
            digest,
        )
        for changes in (
            {"profile": "unverified-other"},
            {"encoding": "zip"},
            {"output_size": -1},
            {"output_sha256": "invalid"},
            {"roundtrip_canonical_digest": canonical_digest(rich_log())},
        ):
            with self.assertRaises((TypeError, ValueError)):
                replace(result, **changes)
        with self.assertRaises(ValueError):
            ExportIssue("", "message")
        with self.assertRaises(TypeError):
            ExportIssue("code", "message", ["not", "tuple"])


if __name__ == "__main__":
    unittest.main()
