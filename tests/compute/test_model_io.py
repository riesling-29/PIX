"""Native model interchange checked against explicit behavioral fixtures.

These tests check persistence boundaries, not discovery quality or soundness.
Document checksums detect alteration; they are not authentication signatures.
"""

import copy
import hashlib
import json
import os
import tempfile
import unittest
import warnings
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch

from pix.compute.model_semantics import fire, fire_binding, model_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import (
    Arc,
    Binding,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.models import (
    ModelArtifact,
    model_document,
    model_from_json,
    model_json_bytes,
    read_model,
    write_model,
)

INVALID = (TypeError, ValueError)
SOURCE = "pix.computation.v1:sha256:" + "a" * 64


def weighted_net():
    """Two distinct transitions share a label; the silent step needs two tokens."""
    return PetriNet(
        places=tuple(Place(name) for name in ("start", "middle", "end")),
        transitions=(
            Transition("tau"),
            Transition("approve-left", "승인"),
            Transition("approve-right", "승인"),
        ),
        arcs=(
            Arc("start", "tau", 2),
            Arc("tau", "middle", 2),
            Arc("middle", "approve-left", 2),
            Arc("approve-left", "end", 2),
            Arc("middle", "approve-right", 2),
            Arc("approve-right", "end", 2),
        ),
        initial_marking=Marking((("start", 2),)),
        final_marking=Marking((("end", 2),)),
    )


def object_net():
    """Joint item/order firing retains an unused object and repeated tokens."""
    return ObjectCentricPetriNet(
        places=(
            TypedPlace("order-in", "order"),
            TypedPlace("order-out", "order"),
            TypedPlace("items-in", "item"),
            TypedPlace("items-out", "item"),
        ),
        transitions=(Transition("ship", "Ship"),),
        arcs=(
            ObjectArc("order-in", "ship"),
            ObjectArc("ship", "order-out"),
            ObjectArc("items-in", "ship", True, 0, 3),
            ObjectArc("ship", "items-out", True, 0, 3),
        ),
        objects=(("o", "order"), ("i1", "item"), ("i2", "item"), ("unused", "item")),
        initial_marking=ObjectMarking(
            (
                ObjectToken("order-in", "o"),
                ObjectToken("items-in", "i1"),
                ObjectToken("items-in", "i1"),
                ObjectToken("items-in", "i2"),
            )
        ),
        final_marking=ObjectMarking(
            (
                ObjectToken("order-out", "o"),
                ObjectToken("items-out", "i1"),
                ObjectToken("items-out", "i2"),
                ObjectToken("items-in", "i1"),
            )
        ),
    )


def repeated_tree():
    activity = ProcessTree("activity", "A")
    return ProcessTree(
        "sequence",
        children=(
            activity,
            ProcessTree(
                "loop",
                children=(
                    ProcessTree("parallel", children=(activity, ProcessTree("tau"))),
                    ProcessTree(
                        "xor", children=(activity, ProcessTree("activity", "B"))
                    ),
                ),
            ),
        ),
    )


def encode_document(document, *, refresh_digest=False):
    """Implement the published envelope digest independently of the decoder."""
    document = copy.deepcopy(document)
    if refresh_digest:
        body = {
            key: value for key, value in document.items() if key != "document_digest"
        }
        canonical = json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        document["document_digest"] = (
            "pix.model-document.v1:sha256:" + hashlib.sha256(canonical).hexdigest()
        )
    return json.dumps(document, ensure_ascii=False).encode("utf-8")


class TestModelRoundtrip(unittest.TestCase):
    def test_weighted_silent_duplicate_label_net_preserves_behavior(self):
        net = weighted_net()
        artifact = model_from_json(model_json_bytes(net, origin="provided"))
        self.assertEqual(artifact.model, net)
        self.assertEqual(artifact.origin, "provided")
        self.assertIsNone(artifact.source_computation_id)
        middle = fire(artifact.model, artifact.model.initial_marking, "tau")
        self.assertEqual(middle, Marking((("middle", 2),)))
        for transition in ("approve-left", "approve-right"):
            with self.subTest(transition=transition):
                self.assertEqual(
                    fire(artifact.model, middle, transition), net.final_marking
                )
        self.assertEqual(model_document(net)["model_digest"], model_digest(net))

    def test_ocpn_variable_bound_universe_and_token_multiplicity_survive(self):
        net = object_net()
        restored = model_from_json(model_json_bytes(net)).model
        self.assertEqual(restored, net)
        self.assertIn(("unused", "item"), restored.objects)
        self.assertEqual(
            restored.initial_marking.tokens.count(ObjectToken("items-in", "i1")), 2
        )
        binding = Binding("ship", (("item", ("i1", "i2")), ("order", ("o",))))
        self.assertEqual(
            fire_binding(restored, restored.initial_marking, binding),
            net.final_marking,
        )
        self.assertEqual(model_document(net)["model_digest"], model_digest(net))

    def test_unbounded_variable_arc_is_not_converted_to_fixed(self):
        net = object_net()
        net = replace(
            net,
            arcs=tuple(
                replace(arc, max_objects=None) if arc.variable else arc
                for arc in net.arcs
            ),
        )
        restored = model_from_json(model_json_bytes(net)).model
        self.assertEqual(restored, net)
        self.assertTrue(
            all(arc.max_objects is None for arc in restored.arcs if arc.variable)
        )

    def test_process_tree_preserves_order_repetition_tau_and_nested_operators(self):
        tree = repeated_tree()
        restored = model_from_json(model_json_bytes(tree)).model
        self.assertEqual(restored, tree)
        self.assertEqual(restored.children[0].activity, "A")
        reversed_tree = replace(tree, children=tuple(reversed(tree.children)))
        self.assertNotEqual(
            model_document(tree)["model_digest"],
            model_document(reversed_tree)["model_digest"],
        )

    def test_supported_envelopes_have_explicit_kind_and_semantics_profile(self):
        fixtures = (
            (weighted_net(), "petri-net", "weighted-place-transition"),
            (
                object_net(),
                "object-centric-petri-net",
                "unit-incidence-concrete-object-universe",
            ),
            (repeated_tree(), "process-tree", "block-structured-tree"),
        )
        for model, kind, profile in fixtures:
            with self.subTest(kind=kind):
                document = model_document(model)
                self.assertEqual(document["format"], "pix.model")
                self.assertEqual(document["version"], "1.0.0")
                self.assertEqual(document["kind"], kind)
                self.assertEqual(document["profile"], profile)
                self.assertRegex(document["model_digest"], r":sha256:[0-9a-f]{64}$")
                self.assertEqual(
                    model_from_json(
                        encode_document(document, refresh_digest=True)
                    ).model,
                    model,
                )

    def test_json_text_and_utf8_bytes_are_equivalent(self):
        encoded = model_json_bytes(weighted_net())
        self.assertIsInstance(encoded, bytes)
        self.assertEqual(model_from_json(encoded), model_from_json(encoded.decode()))

    def test_semantic_identity_ignores_petri_collection_insertion_order(self):
        net = weighted_net()
        reordered = replace(
            net,
            places=tuple(reversed(net.places)),
            transitions=tuple(reversed(net.transitions)),
            arcs=tuple(reversed(net.arcs)),
        )
        self.assertEqual(model_json_bytes(net), model_json_bytes(reordered))

    def test_checksum_covers_provenance_without_changing_model_identity(self):
        net = weighted_net()
        provided = model_document(net, origin="provided")
        discovered = model_document(
            net, origin="discovered", source_computation_id=SOURCE
        )
        self.assertEqual(provided["model_digest"], discovered["model_digest"])
        self.assertNotEqual(provided["document_digest"], discovered["document_digest"])
        altered_source = model_document(
            net, origin="discovered", source_computation_id=SOURCE[:-1] + "b"
        )
        self.assertNotEqual(
            discovered["document_digest"], altered_source["document_digest"]
        )

    def test_artifact_metadata_survives_default_serialization(self):
        original = ModelArtifact(weighted_net(), "discovered", SOURCE)
        restored = model_from_json(model_json_bytes(original))
        self.assertEqual(restored, original)
        self.assertEqual(
            model_json_bytes(original),
            model_json_bytes(
                original, origin="discovered", source_computation_id=SOURCE
            ),
        )

    def test_explicit_conflicting_artifact_metadata_is_rejected(self):
        artifact = ModelArtifact(weighted_net(), "discovered", SOURCE)
        overrides = (
            {"origin": "provided"},
            {"origin": "unspecified"},
            {"source_computation_id": SOURCE[:-1] + "b"},
        )
        for kwargs in overrides:
            with self.subTest(kwargs=kwargs), self.assertRaises(INVALID):
                model_json_bytes(artifact, **kwargs)

    def test_invalid_provenance_is_not_silently_dropped(self):
        cases = (
            ("discovered", None),
            ("discovered", ""),
            ("discovered", "   "),
            ("discovered", "\ud800"),
            ("discovered", 123),
            ("provided", SOURCE),
            ("unspecified", SOURCE),
            ("invented", None),
            (False, None),
        )
        for origin, source in cases:
            with self.subTest(origin=origin, source=source):
                with self.assertRaises(INVALID):
                    ModelArtifact(weighted_net(), origin, source)
                with self.assertRaises(INVALID):
                    model_json_bytes(
                        weighted_net(), origin=origin, source_computation_id=source
                    )

    def test_artifact_and_restored_model_are_immutable(self):
        artifact = model_from_json(model_json_bytes(weighted_net()))
        with self.assertRaises(FrozenInstanceError):
            artifact.origin = "provided"
        with self.assertRaises(FrozenInstanceError):
            artifact.model.transitions = ()
        document = model_document(artifact)
        document["model"]["transitions"][0]["activity"] = "changed externally"
        self.assertEqual(artifact.model, weighted_net())

    def test_constructor_like_labels_remain_ordinary_data(self):
        tree = ProcessTree("activity", "__class__/../../constructor:module")
        self.assertEqual(model_from_json(model_json_bytes(tree)).model, tree)


class TestModelInputValidation(unittest.TestCase):
    def test_truncated_duplicate_key_and_nonfinite_json_are_rejected(self):
        document = model_document(weighted_net())
        encoded = encode_document(document).decode()
        malformed = (
            encoded[:-1],
            encoded + " trailing",
            encoded.replace(
                '"format": "pix.model"', '"format": "pix.model", "format": "pix.model"'
            ),
            encoded.replace('"weight": 2', '"weight": NaN', 1),
            encoded.replace('"weight": 2', '"weight": Infinity', 1),
            encoded.replace('"weight": 2', '"weight": -Infinity', 1),
            "[]",
            "null",
            b"\xff\xfe",
        )
        for value in malformed:
            with self.subTest(value=str(value)[:100]), self.assertRaises(INVALID):
                model_from_json(value)

    def test_duplicate_nested_field_is_rejected_even_if_values_agree(self):
        encoded = encode_document(model_document(weighted_net())).decode()
        duplicated = encoded.replace('"weight": 2', '"weight": 2, "weight": 2', 1)
        self.assertNotEqual(duplicated, encoded)
        with self.assertRaises(INVALID):
            model_from_json(duplicated)

    def test_wrong_input_types_do_not_trigger_coercion(self):
        for value in (None, 123, {}, [], weighted_net()):
            with self.subTest(value=type(value).__name__), self.assertRaises(INVALID):
                model_from_json(value)
        for value in (None, {}, [], "PetriNet", object()):
            with self.subTest(value=type(value).__name__), self.assertRaises(INVALID):
                model_json_bytes(value)

    def test_unknown_envelope_version_kind_and_profile_are_rejected(self):
        changes = (
            ("format", "pickle"),
            ("version", "99.0.0"),
            ("version", 1),
            ("kind", "process-tree"),
            ("kind", "python-object"),
            ("profile", "block-structured-tree"),
            ("profile", "weighted-inhibitor-net"),
        )
        for field, value in changes:
            with self.subTest(field=field, value=value):
                document = model_document(weighted_net())
                document[field] = value
                with self.assertRaises(INVALID):
                    model_from_json(encode_document(document, refresh_digest=True))

    def test_missing_required_envelope_fields_are_rejected(self):
        for field in model_document(weighted_net()):
            with self.subTest(field=field):
                document = model_document(weighted_net())
                del document[field]
                with self.assertRaises(INVALID):
                    model_from_json(encode_document(document))

    def test_checksum_rejects_unannounced_metadata_or_model_alteration(self):
        document = model_document(weighted_net(), origin="provided")
        for region in ("provenance", "model"):
            modified = copy.deepcopy(document)
            if region == "provenance":
                modified[region]["origin"] = "unspecified"
            else:
                modified[region]["transitions"][0]["activity"] = "Different"
            with self.subTest(region=region), self.assertRaises(INVALID):
                model_from_json(encode_document(modified))

    def test_independent_model_digest_rejects_rechecksummed_changed_model(self):
        document = model_document(weighted_net())
        document["model"]["transitions"][0]["activity"] = "Different"
        with self.assertRaises(INVALID):
            model_from_json(encode_document(document, refresh_digest=True))

    def test_unknown_fields_do_not_enable_dynamic_object_construction(self):
        for key in ("__class__", "constructor", "module", "filename", "future_field"):
            for region in ("envelope", "model", "provenance", "transition"):
                with self.subTest(key=key, region=region):
                    document = model_document(weighted_net())
                    target = {
                        "envelope": document,
                        "model": document["model"],
                        "provenance": document["provenance"],
                        "transition": document["model"]["transitions"][0],
                    }[region]
                    target[key] = "../../outside-target"
                    with self.assertRaises(INVALID):
                        model_from_json(encode_document(document, refresh_digest=True))

    def test_malformed_petri_fields_are_rejected_after_envelope_verification(self):
        modifications = (
            ("places", None),
            ("places", ["start"]),
            ("transitions", [{"id": "t", "activity": 3}]),
            ("arcs", [{"source": "start", "target": "tau", "weight": True}]),
            ("arcs", [{"source": "start", "target": "tau", "weight": "2"}]),
            ("arcs", [{"source": "start", "target": "tau", "weight": 2.0}]),
            ("initial_marking", {"tokens": [["start", True]]}),
            ("final_marking", {"tokens": [["unknown", 2]]}),
        )
        for field, value in modifications:
            with self.subTest(field=field, value=value):
                document = model_document(weighted_net())
                document["model"][field] = value
                with self.assertRaises(INVALID):
                    model_from_json(encode_document(document, refresh_digest=True))

    def test_malformed_ocpn_fields_are_rejected_after_envelope_verification(self):
        modifications = (
            ("objects", [["i", "item", "unexpected"]]),
            ("objects", [["i", "item"], ["i", "order"]]),
            (
                "initial_marking",
                {"tokens": [{"place_id": "order-in", "object_id": "i1"}]},
            ),
            (
                "arcs",
                [
                    {
                        "source": "items-in",
                        "target": "ship",
                        "variable": 1,
                        "min_objects": 0,
                        "max_objects": None,
                    }
                ],
            ),
            (
                "arcs",
                [
                    {
                        "source": "items-in",
                        "target": "ship",
                        "variable": True,
                        "min_objects": False,
                        "max_objects": None,
                    }
                ],
            ),
        )
        for field, value in modifications:
            with self.subTest(field=field, value=value):
                document = model_document(object_net())
                document["model"][field] = value
                with self.assertRaises(INVALID):
                    model_from_json(encode_document(document, refresh_digest=True))

    def test_tree_operator_arity_activity_and_extra_fields_are_validated(self):
        malformed = (
            {"operator": "loop", "activity": None, "children": []},
            {"operator": "activity", "activity": True, "children": []},
            {"operator": "tau", "activity": "hidden", "children": []},
            {"operator": "custom_constructor", "activity": None, "children": []},
            {"operator": "tau", "activity": None, "children": [], "__class__": "Path"},
        )
        for tree in malformed:
            with self.subTest(tree=tree):
                document = model_document(repeated_tree())
                document["model"] = tree
                with self.assertRaises(INVALID):
                    model_from_json(encode_document(document, refresh_digest=True))

    def test_rechecksummed_invalid_provenance_is_still_rejected(self):
        invalid = (
            {"origin": "discovered", "source_computation_id": None},
            {"origin": "provided", "source_computation_id": SOURCE},
            {"origin": "unspecified", "source_computation_id": SOURCE},
            {"origin": "provided", "source_computation_id": 123},
            {"origin": "future", "source_computation_id": None},
        )
        for provenance in invalid:
            with self.subTest(provenance=provenance):
                document = model_document(weighted_net())
                document["provenance"] = provenance
                with self.assertRaises(INVALID):
                    model_from_json(encode_document(document, refresh_digest=True))


class TestModelFiles(unittest.TestCase):
    def test_file_roundtrip_uses_explicit_path_and_preserves_metadata(self):
        artifact = ModelArtifact(object_net(), "discovered", SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "모델.arbitrary-suffix"
            published = write_model(artifact, path)
            self.assertEqual(published.path.resolve(), path.resolve())
            self.assertEqual(read_model(published), artifact)
            self.assertEqual(published.byte_count, len(path.read_bytes()))
            self.assertEqual(
                published.output_sha256, hashlib.sha256(path.read_bytes()).hexdigest()
            )
            self.assertEqual(published.cleanup_issues, ())
            with self.assertRaises(FrozenInstanceError):
                published.path = Path(directory) / "changed.json"
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_default_write_preserves_existing_file_and_removes_staging_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_bytes(b"existing user data")
            with self.assertRaises(FileExistsError):
                write_model(weighted_net(), path)
            self.assertEqual(path.read_bytes(), b"existing user data")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_explicit_overwrite_publishes_complete_verified_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_bytes(b"existing user data")
            write_model(repeated_tree(), path, origin="provided", overwrite=True)
            self.assertEqual(
                read_model(path), ModelArtifact(repeated_tree(), "provided")
            )
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_validation_failure_cannot_replace_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_bytes(b"original")
            with self.assertRaises(INVALID):
                write_model(weighted_net(), path, origin="discovered", overwrite=True)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_fsync_failure_leaves_no_published_or_staged_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            with patch(
                "pix._publication.os.fsync", side_effect=OSError("disk failure")
            ):
                with self.assertRaises(OSError):
                    write_model(weighted_net(), path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_atomic_replace_failure_preserves_target_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_bytes(b"original")
            with patch(
                "pix._publication.os.replace", side_effect=OSError("replace failed")
            ):
                with self.assertRaises(OSError):
                    write_model(weighted_net(), path, overwrite=True)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_no_clobber_is_atomic_when_another_writer_wins_publication_race(self):
        original_link = os.link
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"

            def competing_link(source, destination):
                Path(destination).write_bytes(b"concurrent writer")
                return original_link(source, destination)

            with patch("pix._publication.os.link", side_effect=competing_link):
                with self.assertRaises(FileExistsError):
                    write_model(weighted_net(), path)
            self.assertEqual(path.read_bytes(), b"concurrent writer")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_cleanup_failure_preserves_success_even_with_warnings_as_errors(self):
        original_unlink = Path.unlink
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"

            def fail_stage_cleanup(temporary, *args, **kwargs):
                if temporary.name.startswith(".pix-model-"):
                    raise OSError("staging cleanup blocked")
                return original_unlink(temporary, *args, **kwargs)

            with warnings.catch_warnings(record=True) as recorded:
                warnings.simplefilter("error")
                with patch.object(Path, "unlink", fail_stage_cleanup):
                    published = write_model(weighted_net(), path)
            self.assertEqual(recorded, [])
            self.assertEqual(published.path.resolve(), path.resolve())
            self.assertEqual(read_model(published).model, weighted_net())
            self.assertEqual(published.byte_count, len(path.read_bytes()))
            self.assertEqual(
                published.output_sha256, hashlib.sha256(path.read_bytes()).hexdigest()
            )
            self.assertEqual(len(published.cleanup_issues), 1)
            issue = published.cleanup_issues[0]
            self.assertEqual(issue.message, "staging cleanup blocked")
            self.assertEqual(issue.path.parent.resolve(), path.parent.resolve())
            self.assertNotEqual(issue.path, path)
            self.assertTrue(issue.path.exists())
            self.assertEqual(issue.path.read_bytes(), path.read_bytes())

    def test_cleanup_failure_preserves_primary_failure_and_its_evidence(self):
        original_unlink = Path.unlink
        primary = OSError("publication replace failed")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_bytes(b"original")

            def fail_stage_cleanup(temporary, *args, **kwargs):
                if temporary.name.startswith(".pix-model-"):
                    raise OSError("secondary cleanup failure")
                return original_unlink(temporary, *args, **kwargs)

            with warnings.catch_warnings(record=True) as recorded:
                warnings.simplefilter("error")
                with (
                    patch.object(Path, "unlink", fail_stage_cleanup),
                    patch("pix._publication.os.replace", side_effect=primary),
                    self.assertRaises(OSError) as caught,
                ):
                    write_model(weighted_net(), path, overwrite=True)
            self.assertEqual(recorded, [])
            self.assertIs(caught.exception, primary)
            self.assertEqual(str(caught.exception), "publication replace failed")
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(len(caught.exception.cleanup_issues), 1)
            issue = caught.exception.cleanup_issues[0]
            self.assertEqual(issue.message, "secondary cleanup failure")
            self.assertEqual(issue.path.parent.resolve(), path.parent.resolve())
            self.assertNotEqual(issue.path, path)
            self.assertTrue(issue.path.exists())

    def test_overwrite_requires_boolean_and_does_not_coerce_truthy_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            path.write_bytes(b"original")
            for flag in (1, "yes", None):
                with self.subTest(flag=flag), self.assertRaises(TypeError):
                    write_model(weighted_net(), path, overwrite=flag)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_reading_corrupted_file_is_rejected_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            corrupted = model_json_bytes(weighted_net())[:-1]
            path.write_bytes(corrupted)
            with self.assertRaises(INVALID):
                read_model(path)
            self.assertEqual(path.read_bytes(), corrupted)

    def test_missing_source_and_missing_parent_report_filesystem_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing" / "model.json"
            with self.assertRaises(OSError):
                read_model(missing)
            with self.assertRaises(OSError):
                write_model(weighted_net(), missing)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
