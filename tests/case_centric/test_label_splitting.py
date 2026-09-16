"""Hand oracles for contextual distance, modularity and evidence-bound relabeling."""

import json
import unittest
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from math import isnan

from pix.case_centric.label_splitting import (
    AppliedLabelSplitting,
    ContextSimilarity,
    ContextualLabelSplittingSpec,
    LabelContext,
    LabelSplittingApplySpec,
    _communities,
    _edit,
    _similarity,
    apply_label_splitting,
    fit_label_splitting,
    materialize_label_splitting,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseExtension,
    CaseGlobal,
    CaseLog,
    CaseSource,
    CaseTrace,
    case_log_digest,
)
from pix.results import _decode, _encode


def log(*traces):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}:{j}",
                        ()
                        if activity is None
                        else (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(trace)
                ),
            )
            for i, trace in enumerate(traces)
        )
    )


def spec(**kwargs):
    return ContextualLabelSplittingSpec(target_activities=(("x",),), **kwargs)


def context(index, prefix=(), suffix=()):
    return LabelContext(
        index,
        ("x",),
        tuple((a,) for a in prefix),
        tuple((a,) for a in suffix),
        (str(index),),
    )


class ContextDistanceTests(unittest.TestCase):
    def test_token_edit_distance_not_string_character_distance(self):
        self.assertEqual(_edit((("alpha",),), (("alphabeta",),)), 1)
        self.assertEqual(_edit((("a",), ("b",)), (("a",), ("c",), ("b",))), 1)
        self.assertEqual(_edit((), (("a",),)), 1)

    def test_normalized_similarity_hand_values(self):
        left = context(0, ("a", "b"), ("c",))
        right = context(1, ("a", "d"), ("c",))
        self.assertEqual(_similarity(left, right, "concatenated"), Fraction(2, 3))
        self.assertEqual(_similarity(left, right, "sided"), Fraction(2, 3))
        self.assertEqual(_similarity(context(2), context(3), "concatenated"), 1)
        self.assertEqual(_similarity(context(2), context(3, ("a",)), "concatenated"), 0)

    def test_side_ambiguity_is_explicit_profile_difference(self):
        before, after = context(0, ("a",)), context(1, (), ("a",))
        self.assertEqual(_similarity(before, after, "concatenated"), 1)
        self.assertEqual(_similarity(before, after, "sided"), 0)
        source = log(("a", "x"), ("x", "a"))
        concatenated = fit_label_splitting(
            source, spec(prefix_length=1, suffix_length=1)
        )
        sided = fit_label_splitting(
            source, spec(prefix_length=1, suffix_length=1, distance="sided")
        )
        self.assertEqual(len(concatenated.value.clusters), 1)
        self.assertEqual(len(concatenated.value.contexts), 1)
        self.assertEqual(len(concatenated.value.contexts[0].windows), 2)
        self.assertEqual(concatenated.value.edges, ())
        self.assertEqual(len(sided.value.clusters), 2)

    def test_threshold_is_strict(self):
        source = log(("a", "x", "b"), ("a", "x", "c"))
        at = fit_label_splitting(
            source, spec(prefix_length=1, suffix_length=1, min_similarity=0.5)
        )
        below = fit_label_splitting(
            source, spec(prefix_length=1, suffix_length=1, min_similarity=0.49)
        )
        self.assertEqual(at.value.edges, ())
        self.assertEqual(len(at.value.clusters), 2)
        self.assertEqual(below.value.edges, (ContextSimilarity(0, 1, 1, 2),))
        self.assertEqual(len(below.value.clusters), 1)

    def test_zero_length_contexts_merge_identical_occurrences(self):
        result = fit_label_splitting(
            log(("a", "x"), ("x", "b")), spec(prefix_length=0, suffix_length=0)
        )
        self.assertEqual(len(result.value.contexts), 1)
        self.assertEqual(result.value.clusters[0].event_count, 2)

    def test_graph_modularity_does_not_use_connected_components(self):
        # Two unit triangles joined by a 1/10 bridge. A connected-component
        # surrogate would return ONE cluster; modularity gives the two triangles.
        nodes = tuple(context(i) for i in range(6))
        edges = tuple(
            ContextSimilarity(a, b, 1, 1)
            for a, b in ((0, 1), (0, 2), (1, 2), (3, 4), (3, 5), (4, 5))
        ) + (ContextSimilarity(2, 3, 1, 10),)
        self.assertEqual(_communities(nodes, edges), ((0, 1, 2), (3, 4, 5)))

    def test_modularity_transitive_ties_and_isolates(self):
        nodes = tuple(context(i) for i in range(5))
        # Path of four nodes has tied end-edge gain 2/9; lexicographic tie
        # picks (0,1), then (2,3). Final merge would reduce Q by 1/6.
        edges = tuple(ContextSimilarity(i, i + 1, 1, 1) for i in range(3))
        self.assertEqual(_communities(nodes, edges), ((0, 1), (2, 3), (4,)))
        self.assertEqual(
            _communities(nodes, tuple(reversed(edges))), ((0, 1), (2, 3), (4,))
        )

    def test_no_edges_keeps_distinct_contexts(self):
        result = fit_label_splitting(
            log(("a", "x"), ("b", "x")), spec(prefix_length=1, suffix_length=0)
        )
        self.assertEqual(result.value.edges, ())
        self.assertEqual(len(result.value.clusters), 2)


class ContextFitApplyTests(unittest.TestCase):
    def setUp(self):
        self.source = log(("a", "x", "b"), ("c", "x", "d"), ("a", "x", "b"))
        self.fit = fit_label_splitting(
            self.source, spec(prefix_length=1, suffix_length=1)
        )

    def test_frequency_ranking_and_context_occurrences(self):
        clusters = self.fit.value.clusters
        self.assertEqual(tuple(c.event_count for c in clusters), (2, 1))
        self.assertEqual(json.loads(clusters[0].derived_label)[2], 0)
        self.assertEqual(self.fit.value.eligible_count, 3)
        self.assertEqual(self.fit.value.excluded_count, 0)
        self.assertEqual(self.fit.value.event_count, 9)

    def test_fit_is_immutable_and_does_not_mutate_source(self):
        digest = case_log_digest(self.source)
        with self.assertRaises(FrozenInstanceError):
            self.fit.value.event_count = 0
        self.assertEqual(case_log_digest(self.source), digest)
        self.assertIsNone(
            self.source.traces[0].events[1].attribute(self.fit.spec.output_key)
        )

    def test_same_log_application_has_no_unseen_contexts(self):
        applied = apply_label_splitting(self.source, self.fit, training_log=self.source)
        self.assertEqual(applied.status, ComputeStatus.COMPUTED)
        self.assertEqual(applied.value.known_count, 3)
        self.assertEqual(applied.value.unseen_count, 0)
        self.assertEqual(applied.parent_computation_ids, (self.fit.computation_id,))

    def test_new_log_uses_learned_ids_with_new_lineage(self):
        current = log(("c", "x", "d"))
        applied = apply_label_splitting(current, self.fit, training_log=self.source)
        known = applied.value.lineage[1]
        self.assertEqual(known.disposition, "known")
        self.assertEqual(known.event_id, "e0:1")
        self.assertEqual(known.derived_label, self.fit.value.clusters[1].derived_label)
        self.assertNotEqual(applied.source_digest, self.fit.source_digest)

    def test_unseen_context_retains_original_without_guessing(self):
        current = log(("a", "x", "d"))
        applied = apply_label_splitting(current, self.fit, training_log=self.source)
        self.assertEqual(applied.status, ComputeStatus.PARTIAL)
        row = applied.value.lineage[1]
        self.assertEqual(row.disposition, "unseen_context")
        self.assertIsNone(row.cluster_id)
        self.assertEqual(
            json.loads(row.derived_label), ["pix.contextual.v1", ["x"], None]
        )

    def test_unseen_context_can_fail_explicitly(self):
        applied = apply_label_splitting(
            log(("a", "x", "d")),
            self.fit,
            training_log=self.source,
            spec=LabelSplittingApplySpec("error"),
        )
        self.assertEqual(applied.status, ComputeStatus.INVALID_INPUT)
        self.assertIsNone(applied.value)

    def test_unseen_activity_is_distinguished(self):
        fitted = fit_label_splitting(log(("a",)))
        applied = apply_label_splitting(log(("b",)), fitted, training_log=log(("a",)))
        self.assertEqual(applied.value.lineage[0].disposition, "unseen_activity")

    def test_original_labels_that_look_derived_do_not_collide(self):
        hostile = self.fit.value.clusters[0].derived_label
        current = log((hostile,), ("a", "x", "b"))
        applied = apply_label_splitting(current, self.fit, training_log=self.source)
        self.assertNotEqual(
            applied.value.lineage[0].derived_label,
            applied.value.lineage[2].derived_label,
        )
        self.assertEqual(
            json.loads(applied.value.lineage[0].derived_label)[1], [hostile]
        )

    def test_equal_frequency_rank_is_independent_of_trace_order(self):
        source = log(("c", "x", "d"), ("a", "x", "b"))
        first = fit_label_splitting(source, self.fit.spec)
        second = fit_label_splitting(
            replace(source, traces=tuple(reversed(source.traces))), self.fit.spec
        )
        self.assertEqual(first.value.contexts, second.value.contexts)
        self.assertEqual(first.value.clusters, second.value.clusters)

    def test_empty_log_is_computed_empty_model(self):
        source = log(())
        fitted = fit_label_splitting(source)
        applied = apply_label_splitting(source, fitted, training_log=source)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertEqual(fitted.status, ComputeStatus.COMPUTED)
        self.assertEqual(derived.traces, source.traces)
        self.assertEqual(fitted.value.contexts, ())

    def test_context_budget_never_returns_incomplete_model(self):
        fitted = fit_label_splitting(self.source, spec(max_contexts=1))
        self.assertEqual(fitted.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(fitted.issues[0].code, "context_limit")
        self.assertIsNone(fitted.value)

    def test_model_payload_json_roundtrip(self):
        encoded = json.loads(json.dumps(_encode(self.fit.value), allow_nan=False))
        self.assertEqual(_decode(encoded, type(self.fit.value)), self.fit.value)
        applied = apply_label_splitting(self.source, self.fit, training_log=self.source)
        encoded = json.loads(json.dumps(_encode(applied.value), allow_nan=False))
        self.assertEqual(_decode(encoded, AppliedLabelSplitting), applied.value)
        self.assertEqual(
            _decode(_encode(applied.spec), type(applied.spec)), applied.spec
        )


class ClassificationPreservationTests(unittest.TestCase):
    def test_non_target_activity_needs_no_context_to_be_retained(self):
        source = log((None, "a", "x"))
        fitted = fit_label_splitting(source, spec(prefix_length=1, suffix_length=0))
        self.assertEqual(fitted.value.lineage[1].disposition, "not_targeted")
        self.assertEqual(json.loads(fitted.value.lineage[1].derived_label)[1], ["a"])
        self.assertEqual(fitted.value.excluded_count, 1)
        applied = apply_label_splitting(source, fitted, training_log=source)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertIsNotNone(
            derived.traces[0].events[1].attribute(fitted.spec.output_key)
        )

    def test_event_globals_and_explicit_override(self):
        source = replace(
            log((None, "x")),
            globals=(
                CaseGlobal(
                    "event", (CaseAttribute("concept:name", "string", "global"),)
                ),
            ),
        )
        fitted = fit_label_splitting(source)
        self.assertEqual(
            tuple(row.original for row in fitted.value.lineage), (("global",), ("x",))
        )
        applied = apply_label_splitting(source, fitted, training_log=source)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertIsNone(derived.traces[0].events[0].attribute("concept:name"))
        self.assertEqual(
            derived.attribute(derived.traces[0].events[0], "concept:name").value,
            "global",
        )
        self.assertEqual(derived.globals, source.globals)

    def test_classifier_with_global_component_preserves_classifiers(self):
        source = replace(
            log(("x", "x")),
            globals=(
                CaseGlobal(
                    "event",
                    (CaseAttribute("lifecycle:transition", "string", "complete"),),
                ),
            ),
            classifiers=(
                CaseClassifier(
                    "activity lifecycle",
                    ("concept:name", "lifecycle:transition"),
                    lexical="'concept:name' 'lifecycle:transition'",
                ),
            ),
        )
        fitted = fit_label_splitting(
            source, ContextualLabelSplittingSpec(classifier="activity lifecycle")
        )
        self.assertEqual(
            fitted.value.classifier_keys, ("concept:name", "lifecycle:transition")
        )
        self.assertEqual(fitted.value.lineage[0].original, ("x", "complete"))
        applied = apply_label_splitting(source, fitted, training_log=source)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertEqual(derived.classifiers[:-1], source.classifiers)
        self.assertEqual(derived.classifiers[-1].keys, (fitted.spec.output_key,))

    def test_classifier_redefinition_on_new_log_rejected(self):
        source = replace(
            log(("x",)), classifiers=(CaseClassifier("name", ("concept:name",)),)
        )
        fitted = fit_label_splitting(
            source, ContextualLabelSplittingSpec(classifier="name")
        )
        changed = replace(source, classifiers=(CaseClassifier("name", ("other",)),))
        applied = apply_label_splitting(changed, fitted, training_log=source)
        self.assertEqual(applied.status, ComputeStatus.INVALID_INPUT)

    def test_missing_positions_are_never_collapsed(self):
        source = log(("a", None, "x", "b", "x"))
        fitted = fit_label_splitting(source, spec(prefix_length=1, suffix_length=0))
        rows = fitted.value.lineage
        self.assertEqual(rows[1].disposition, "missing_activity")
        self.assertEqual(rows[2].disposition, "incomplete_context")
        self.assertEqual(rows[4].prefix, (("b",),))
        self.assertEqual(fitted.value.excluded_count, 2)
        self.assertEqual(fitted.value.eligible_count, 1)
        applied = apply_label_splitting(source, fitted, training_log=source)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertEqual(
            tuple(e.id for e in derived.traces[0].events),
            tuple(e.id for e in source.traces[0].events),
        )
        self.assertEqual(
            derived.traces[0].events[2].attributes,
            source.traces[0].events[2].attributes,
        )

    def test_nonfinite_unrelated_raw_facts_remain_outside_result(self):
        raw = CaseAttribute("raw", "float", float("nan"), lexical="NaN")
        nested = CaseAttribute(
            "nested", "list", values=(CaseAttribute("", "string", "v", lexical="v"),)
        )
        source = replace(
            log(("x",)),
            traces=(
                CaseTrace(
                    "c",
                    (
                        CaseEvent(
                            "e",
                            (
                                CaseAttribute(
                                    "concept:name", "string", "x", lexical="&#120;"
                                ),
                                raw,
                                nested,
                            ),
                        ),
                    ),
                    (CaseAttribute("trace-meta", "int", 1, lexical="001"),),
                ),
            ),
            attributes=(CaseAttribute("log-meta", "string", "m"),),
            metadata=(("source-hint", "keep"),),
            source=CaseSource("original.xes", "xes", "a" * 64, 123),
            extensions=(
                CaseExtension("concept", "concept", "http://example.org/concept"),
            ),
        )
        fitted = fit_label_splitting(source)
        applied = apply_label_splitting(source, fitted, training_log=source)
        json.dumps(_encode(fitted.value), allow_nan=False)
        json.dumps(_encode(applied.value), allow_nan=False)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertEqual(
            derived.traces[0].events[0].attributes[:-1],
            source.traces[0].events[0].attributes,
        )
        self.assertTrue(isnan(derived.traces[0].events[0].attribute("raw").value))
        self.assertIs(derived.source, source.source)
        self.assertEqual(derived.attributes, source.attributes)
        self.assertEqual(derived.extensions, source.extensions)
        self.assertEqual(derived.metadata[:1], source.metadata)
        self.assertEqual(derived.traces[0].attributes, source.traces[0].attributes)

    def test_duplicate_source_attribute_is_invalid(self):
        source = CaseLog(
            (
                CaseTrace(
                    "c",
                    (
                        CaseEvent(
                            "e",
                            (
                                CaseAttribute("concept:name", "string", "a"),
                                CaseAttribute("concept:name", "string", "b"),
                            ),
                        ),
                    ),
                ),
            )
        )
        fitted = fit_label_splitting(source)
        self.assertEqual(fitted.status, ComputeStatus.INVALID_INPUT)

    def test_blank_or_numeric_classification_is_excluded(self):
        source = CaseLog(
            (
                CaseTrace(
                    "c",
                    (
                        CaseEvent("a", (CaseAttribute("concept:name", "string", " "),)),
                        CaseEvent("b", (CaseAttribute("concept:name", "int", 3),)),
                    ),
                ),
            )
        )
        fitted = fit_label_splitting(source)
        self.assertEqual(fitted.value.excluded_count, 2)
        self.assertEqual(fitted.status, ComputeStatus.PARTIAL)

    def test_existing_target_global_is_not_overwritten(self):
        source = replace(
            log(("x",)),
            globals=(
                CaseGlobal(
                    "event",
                    (CaseAttribute("pix:contextual:activity", "string", "existing"),),
                ),
            ),
        )
        fitted = fit_label_splitting(source)
        self.assertEqual(fitted.status, ComputeStatus.INVALID_INPUT)

    def test_source_target_attribute_collision_is_invalid(self):
        fitted = fit_label_splitting(
            log(("x",)), ContextualLabelSplittingSpec(output_key="concept:name")
        )
        self.assertEqual(fitted.status, ComputeStatus.INVALID_INPUT)

    def test_derived_classifier_name_collision_gets_fresh_name(self):
        source = replace(
            log(("x",)),
            classifiers=(CaseClassifier("PIX contextual activity", ("concept:name",)),),
        )
        fitted = fit_label_splitting(source)
        applied = apply_label_splitting(source, fitted, training_log=source)
        derived = materialize_label_splitting(
            source, fitted, applied, training_log=source
        )
        self.assertEqual(derived.classifiers[-1].name, "PIX contextual activity 2")


class EvidenceValidationTests(unittest.TestCase):
    def test_numerically_equal_wrong_payload_types_are_rejected(self):
        source = log(("x",))
        fitted = fit_label_splitting(source)
        applied = apply_label_splitting(source, fitted, training_log=source)
        for bad_count in (True, 1.0):
            with self.subTest(bad_count=bad_count):
                forged_fit = replace(
                    fitted, value=replace(fitted.value, event_count=bad_count)
                )
                with self.assertRaisesRegex(ValueError, "fit evidence"):
                    apply_label_splitting(source, forged_fit, training_log=source)
                forged_apply = replace(
                    applied, value=replace(applied.value, event_count=bad_count)
                )
                with self.assertRaisesRegex(ValueError, "application evidence"):
                    materialize_label_splitting(
                        source, fitted, forged_apply, training_log=source
                    )

    def test_numerically_equal_wrong_lineage_id_type_is_rejected(self):
        source = log(("x",))
        fitted = fit_label_splitting(source)
        applied = apply_label_splitting(source, fitted, training_log=source)
        row = replace(applied.value.lineage[0], event_index=False)
        forged = replace(applied, value=replace(applied.value, lineage=(row,)))
        with self.assertRaisesRegex(ValueError, "application evidence"):
            materialize_label_splitting(source, fitted, forged, training_log=source)

    def setUp(self):
        self.source = log(("a", "x"), ("b", "x"))
        self.fit = fit_label_splitting(
            self.source, spec(prefix_length=1, suffix_length=0)
        )
        self.applied = apply_label_splitting(
            self.source, self.fit, training_log=self.source
        )

    def test_fit_payload_tampering_rejected(self):
        forged = replace(self.fit, value=replace(self.fit.value, event_count=900))
        with self.assertRaisesRegex(ValueError, "fit evidence"):
            apply_label_splitting(self.source, forged, training_log=self.source)

    def test_fit_request_id_and_version_tampering_rejected(self):
        for forged in (
            replace(self.fit, computation_id="forged"),
            replace(self.fit, operator_version="9"),
            replace(self.fit, operator_id="another.operator"),
            replace(self.fit, spec=replace(self.fit.spec, min_similarity=0.5)),
        ):
            with self.subTest(forged=forged.operator_id):
                with self.assertRaisesRegex(ValueError, "fit evidence"):
                    apply_label_splitting(self.source, forged, training_log=self.source)

    def test_wrong_training_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "fit evidence"):
            apply_label_splitting(
                self.source, self.fit, training_log=log(("different",))
            )

    def test_apply_payload_tampering_rejected(self):
        rows = self.applied.value.lineage
        forged = replace(
            self.applied,
            value=replace(
                self.applied.value,
                lineage=(replace(rows[0], derived_label="forged"),) + rows[1:],
            ),
        )
        with self.assertRaisesRegex(ValueError, "application evidence"):
            materialize_label_splitting(
                self.source, self.fit, forged, training_log=self.source
            )

    def test_apply_identity_parent_source_and_request_tampering_rejected(self):
        for forged in (
            replace(self.applied, computation_id="forged"),
            replace(self.applied, parent_computation_ids=("forged",)),
            replace(self.applied, source_digest="forged"),
            replace(
                self.applied,
                spec=replace(self.applied.spec, training_source_digest="forged"),
            ),
        ):
            with self.subTest(forged=forged.computation_id):
                with self.assertRaisesRegex(ValueError, "application evidence"):
                    materialize_label_splitting(
                        self.source, self.fit, forged, training_log=self.source
                    )

    def test_source_lexical_facts_change_invalidates_evidence(self):
        old_trace = self.source.traces[0]
        old_event = old_trace.events[0]
        changed_event = replace(
            old_event, attributes=(replace(old_event.attributes[0], lexical="&#97;"),)
        )
        changed = replace(
            self.source,
            traces=(replace(old_trace, events=(changed_event,) + old_trace.events[1:]),)
            + self.source.traces[1:],
        )
        with self.assertRaisesRegex(ValueError, "application evidence"):
            materialize_label_splitting(
                changed, self.fit, self.applied, training_log=self.source
            )

    def test_failed_application_cannot_materialize(self):
        failed = apply_label_splitting(
            log(("q", "x")),
            self.fit,
            training_log=self.source,
            spec=LabelSplittingApplySpec("error"),
        )
        with self.assertRaisesRegex(ValueError, "successful application"):
            materialize_label_splitting(
                log(("q", "x")), self.fit, failed, training_log=self.source
            )

    def test_invalid_spec_values_are_rejected(self):
        for kwargs in (
            {"prefix_length": True},
            {"suffix_length": -1},
            {"min_similarity": float("nan")},
            {"min_similarity": 1.1},
            {"distance": "components"},
            {"max_contexts": 0},
            {"activity_keys": ("x", "x")},
            {"target_activities": (("x",), ("x",))},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((TypeError, ValueError)):
                    ContextualLabelSplittingSpec(**kwargs)


if __name__ == "__main__":
    unittest.main()
