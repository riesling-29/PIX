"""Hand-derived OCDFG comparison goldens; upstream is never imported/executed.

The independent derivation is recorded in
.artifacts/union-2026-09-15/ocdfg_oracle.md. Assertions distinguish typed
conformance from the pinned reference's untyped missing-only formula.
"""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

import pix.results as persistence
from pix.compute.context import ComputationContext
from pix.compute.ocdfg import discover_ocdfg
from pix.contracts.analysis import ObjectCentricDFG, OCDFGSpec
from pix.contracts.result import ComputeStatus
from pix.object_centric.graph_comparison import (
    OCDFGComparisonSpec,
    compare_ocdfgs,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def log(objects, rows, *, declared=()):
    """Rows are (activity, participating-object-IDs), in strict timestamp order."""
    return OCEL(
        event_types=tuple(EventType(name) for name in sorted({r[0] for r in rows})),
        object_types=tuple(
            ObjectType(name) for name in sorted(set(objects.values()) | set(declared))
        ),
        objects=tuple(Object(oid, kind) for oid, kind in objects.items()),
        events=tuple(
            Event(f"e{i}", activity, T0 + timedelta(seconds=i))
            for i, (activity, _) in enumerate(rows)
        ),
        e2o=tuple(
            E2O(f"e{i}", oid, "flow")
            for i, (_, participants) in enumerate(rows)
            for oid in participants
        ),
    )


def ab():
    return log({"t": "T"}, (("A", ("t",)), ("B", ("t",))))


def graph(value):
    result = discover_ocdfg(
        value, OCDFGSpec(tuple(row.name for row in value.object_types))
    )
    if result.status != ComputeStatus.COMPUTED:
        raise AssertionError(result)
    return result.value


def fraction(score):
    if score.score_numerator is None:
        return None
    return Fraction(score.score_numerator, score.score_denominator)


class OCDFGGoldenTests(unittest.TestCase):
    def compare(self, real, normative, expected, *, profile="typed_symmetric", **kw):
        result = compare_ocdfgs(
            real, normative, OCDFGComparisonSpec(profile=profile, **kw)
        )
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(fraction(result.value.score), expected)
        return result

    def test_identity_has_explicit_domains_and_zero_penalty(self):
        for profile, normalization in (
            ("reference_untyped", 6),
            ("typed_symmetric", 7),
        ):
            with self.subTest(profile=profile):
                value = self.compare(ab(), ab(), Fraction(1), profile=profile).value
                self.assertEqual(value.activity_domain_count, 2)
                self.assertEqual(value.flow_domain_count, 1)
                self.assertEqual(value.object_type_domain_count, 1)
                self.assertEqual(value.score.penalty_numerator, 0)
                self.assertEqual(value.score.normalization_numerator, normalization)

    def test_swapped_type_assignments_reference_hides_typed_failure(self):
        objects = {"t": "T", "u": "U"}
        normative = log(
            objects, (("A", ("t",)), ("B", ("t",)), ("C", ("u",)), ("D", ("u",)))
        )
        real = log(
            objects, (("A", ("u",)), ("B", ("u",)), ("C", ("t",)), ("D", ("t",)))
        )
        self.compare(real, normative, Fraction(1), profile="reference_untyped")
        value = self.compare(real, normative, Fraction(1, 13)).value
        self.assertEqual(value.activity_domain_count, 8)
        self.assertEqual(value.flow_domain_count, 4)
        self.assertEqual(value.activity_structural_defects, 8)
        self.assertEqual(value.flow_structural_defects, 4)
        self.assertEqual(value.type_structural_defects, 0)
        self.assertEqual(set(value.missing_flows), {("T", "A", "B"), ("U", "C", "D")})
        self.assertEqual(
            set(value.additional_flows), {("U", "A", "B"), ("T", "C", "D")}
        )
        self.compare(
            real, normative, Fraction(7, 13), activity_threshold=1, flow_threshold=1
        )

    def test_shared_pair_same_type_does_not_count_objects_as_event_pairs(self):
        two = log({"a": "T", "b": "T"}, (("A", ("a", "b")), ("B", ("a", "b"))))
        for profile in ("reference_untyped", "typed_symmetric"):
            with self.subTest(profile=profile):
                value = self.compare(ab(), two, Fraction(1), profile=profile).value
                self.assertEqual(value.normative.flows[0].event_pairs, 1)
                self.assertEqual(value.normative.flows[0].objects, 2)
                self.assertEqual(value.normative.flows[0].occurrences, 2)

    def test_object_and_occurrence_measures_are_explicit_alternatives(self):
        two = log({"a": "T", "b": "T"}, (("A", ("a", "b")), ("B", ("a", "b"))))
        for activity_measure, flow_measure in (
            ("objects", "objects"),
            ("occurrences", "occurrences"),
        ):
            with self.subTest(activity=activity_measure, flow=flow_measure):
                value = self.compare(
                    ab(),
                    two,
                    Fraction(4, 7),
                    activity_measure=activity_measure,
                    flow_measure=flow_measure,
                ).value
                self.assertEqual(value.activity_measure_defects, 2)
                self.assertEqual(value.flow_measure_defects, 1)

    def test_shared_pair_across_types_is_summed_in_reference(self):
        objects = {"t": "T", "u": "U"}
        normative = log(objects, (("A", ("t", "u")), ("B", ("t", "u"))))
        real = log(objects, (("A", ("t",)), ("B", ("t",))))
        reference = self.compare(
            real, normative, Fraction(5, 6), profile="reference_untyped"
        ).value
        self.assertEqual(reference.activity_measure_defects, 0)
        self.assertEqual(reference.flow_differences[0].observed, 1)
        self.assertEqual(reference.flow_differences[0].normative, 2)
        self.compare(real, normative, Fraction(4, 7))
        self.compare(real, normative, Fraction(9, 14), flow_threshold=1)
        self.compare(
            real, normative, Fraction(11, 14), activity_threshold=1, flow_threshold=1
        )
        self.compare(
            real, normative, Fraction(1), profile="reference_untyped", flow_threshold=1
        )

    def test_qualifier_duplicates_preserve_participation_multiplicity(self):
        base = ab()
        extra_roles = replace(
            base,
            e2o=base.e2o
            + tuple(E2O(row.event, row.object, "audit") for row in base.e2o),
        )
        value = self.compare(
            extra_roles,
            base,
            Fraction(1),
            activity_measure="occurrences",
            flow_measure="occurrences",
        ).value
        self.assertEqual(value.observed.activities[0].occurrences, 1)
        self.assertEqual(value.observed.flows[0].occurrences, 1)
        self.compare(extra_roles, base, Fraction(1), qualifiers=("flow",))

    def test_activity_only_frequency_difference_and_strict_threshold(self):
        real = log(
            {"t": "T", "extra": "T"}, (("A", ("t",)), ("B", ("t",)), ("A", ("extra",)))
        )
        self.compare(real, ab(), Fraction(5, 6), profile="reference_untyped")
        value = self.compare(real, ab(), Fraction(6, 7)).value
        self.assertEqual(value.flow_measure_defects, 0)
        self.assertEqual(value.activity_measure_defects, 1)
        equal = self.compare(real, ab(), Fraction(1), activity_threshold=1).value
        row = next(
            item for item in equal.activity_differences if item.key == ("T", "A")
        )
        self.assertEqual(row.absolute_difference, 1)
        self.assertFalse(row.exceeds_threshold)
        self.compare(real, ab(), Fraction(6, 7), activity_threshold=0.999)

    def test_frequency_penalty_is_binary_not_count_difference(self):
        objects = {"t": "T", **{f"extra{i}": "T" for i in range(100)}}
        rows = (("A", ("t",)), ("B", ("t",))) + tuple(
            ("A", (f"extra{i}",)) for i in range(100)
        )
        real = log(objects, rows)
        value = self.compare(real, ab(), Fraction(6, 7)).value
        self.assertEqual(value.activity_differences[0].absolute_difference, 100)
        self.compare(real, ab(), Fraction(5, 6), profile="reference_untyped")
        self.compare(real, ab(), Fraction(1), activity_threshold=100)

    def test_missing_structure_reference_is_directional_typed_is_symmetric(self):
        shorter = log({"t": "T"}, (("A", ("t",)),))
        self.compare(shorter, ab(), Fraction(1, 3), profile="reference_untyped")
        self.compare(ab(), shorter, Fraction(2, 3), profile="reference_untyped")
        forward = self.compare(shorter, ab(), Fraction(3, 7)).value
        backward = self.compare(ab(), shorter, Fraction(3, 7)).value
        self.assertEqual(forward.missing_activities, (("T", "B"),))
        self.assertEqual(backward.additional_activities, (("T", "B"),))
        self.compare(
            shorter, ab(), Fraction(5, 7), activity_threshold=1, flow_threshold=1
        )
        self.compare(
            ab(), shorter, Fraction(5, 7), activity_threshold=1, flow_threshold=1
        )

    def test_additional_structure_diagnostic_remains_when_reference_score_is_one(self):
        real = log(
            {"t": "T", "extra": "T"}, (("A", ("t",)), ("B", ("t",)), ("C", ("extra",)))
        )
        reference = self.compare(
            real, ab(), Fraction(1), profile="reference_untyped", activity_threshold=1
        ).value
        self.assertEqual(reference.additional_activities, (("C",),))
        self.assertEqual(reference.activity_structural_defects, 0)
        self.compare(real, ab(), Fraction(8, 9), activity_threshold=1)
        self.compare(real, ab(), Fraction(7, 8), profile="reference_untyped")
        self.compare(real, ab(), Fraction(7, 9))

    def test_empty_domain_requires_explicit_one_convention_in_both_profiles(self):
        empty = log({}, ())
        for profile in ("typed_symmetric", "reference_untyped"):
            with self.subTest(profile=profile):
                value = self.compare(empty, empty, None, profile=profile).value
                self.assertTrue(value.score.zero_domain)
                self.assertIsNone(value.score.value)
                self.compare(
                    empty, empty, Fraction(1), profile=profile, zero_domain="one"
                )

    def test_isolated_object_type_change_is_visible_only_in_typed_domain(self):
        real, normative = log({"u": "U"}, ()), log({"t": "T"}, ())
        typed = self.compare(real, normative, Fraction(0)).value
        self.assertEqual(typed.missing_object_types, ("T",))
        self.assertEqual(typed.additional_object_types, ("U",))
        self.assertEqual(typed.activity_domain_count, 0)
        self.compare(
            real, normative, Fraction(1), profile="reference_untyped", zero_domain="one"
        )

    def test_unused_schema_types_do_not_create_a_comparison_domain(self):
        empty = log({}, (), declared=("DeclaredButAbsent",))
        self.compare(empty, log({}, ()), None)
        isolated = log({"t": "T"}, (), declared=("DeclaredButAbsent",))
        value = self.compare(isolated, isolated, Fraction(1)).value
        self.assertEqual(value.object_type_domain_count, 1)
        self.assertEqual(value.observed.object_types, ("T",))

    def test_orphan_vs_connected_activity_has_different_reference_frequency(self):
        orphan = log({}, (("A", ()),))
        connected = log({"t": "T"}, (("A", ("t",)),))
        reference = self.compare(
            connected, orphan, Fraction(1, 2), profile="reference_untyped"
        ).value
        self.assertEqual(reference.activity_differences[0].normative, 0)
        self.assertEqual(reference.activity_differences[0].observed, 1)
        self.compare(connected, orphan, Fraction(0))

    def test_raw_orphan_counts_are_preserved_only_by_typed_profile(self):
        one = log({}, (("A", ()),))
        two = log({}, (("A", ()), ("A", ())))
        self.compare(two, one, Fraction(1), profile="reference_untyped")
        value = self.compare(two, one, Fraction(1, 2)).value
        self.assertEqual(value.activity_differences[0].key, (None, "A"))
        self.assertEqual(value.activity_differences[0].observed, 2)
        self.assertEqual(value.activity_differences[0].normative, 1)

    def test_orphan_bucket_survives_same_label_connected_incidence(self):
        connected = log({"t": "T"}, (("A", ("t",)),))
        mixed = log({"t": "T"}, (("A", ("t",)), ("A", ())))
        value = self.compare(mixed, connected, Fraction(3, 5)).value
        self.assertEqual(value.additional_activities, ((None, "A"),))
        self.compare(mixed, connected, Fraction(1), profile="reference_untyped")

    def test_decimal_weights_preserve_exact_rational_score(self):
        real = log(
            {"t": "T", "extra": "T"}, (("A", ("t",)), ("B", ("t",)), ("A", ("extra",)))
        )
        value = self.compare(
            real,
            ab(),
            Fraction(43, 44),
            activity_measure_weight=0.1,
            flow_measure_weight=0.2,
        ).value
        # D = 1 + 2 + 1 + 0.1*2 + 0.2*1 = 4.4, P = 0.1.
        self.assertEqual(
            Fraction(value.score.penalty_numerator, value.score.penalty_denominator),
            Fraction(1, 10),
        )

    def test_all_zero_weights_do_not_invent_evidence(self):
        weights = dict(
            activity_structure_weight=0,
            flow_structure_weight=0,
            activity_measure_weight=0,
            flow_measure_weight=0,
            object_type_weight=0,
        )
        self.compare(ab(), ab(), None, **weights)
        self.compare(ab(), ab(), Fraction(1), zero_domain="one", **weights)


class OCDFGInputTests(unittest.TestCase):
    def test_timestamp_ties_are_unavailable_unless_explicitly_broken(self):
        base = ab()
        tied = replace(
            base, events=tuple(replace(event, time=T0) for event in base.events)
        )
        result = compare_ocdfgs(tied, base)
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertTrue(any("ambiguous" in item.code for item in result.issues))
        explicit = compare_ocdfgs(
            tied, base, OCDFGComparisonSpec(tie_policy="event_id")
        )
        self.assertEqual(explicit.status, ComputeStatus.COMPUTED)
        self.assertEqual(fraction(explicit.value.score), Fraction(1))

    def test_context_input_has_same_result_as_log(self):
        source = ab()
        self.assertEqual(
            compare_ocdfgs(source, source),
            compare_ocdfgs(ComputationContext.build(source), source),
        )

    def test_graph_and_log_aggregates_agree_when_no_orphan_activity_exists(self):
        source = ab()
        derived = graph(source)
        raw_result = compare_ocdfgs(source, source)
        graph_result = compare_ocdfgs(derived, derived)
        self.assertEqual(raw_result.value.score, graph_result.value.score)
        self.assertEqual(raw_result.value.observed.activity_universe, "source_events")
        self.assertEqual(
            graph_result.value.observed.activity_universe, "graph_participation"
        )
        self.assertNotEqual(raw_result.source_digest, graph_result.source_digest)

    def test_graph_input_cannot_recover_raw_orphan_domain(self):
        source = log({"t": "T"}, (("A", ("t",)), ("B", ())))
        derived = graph(source)
        raw = compare_ocdfgs(source, source).value
        projected = compare_ocdfgs(derived, derived).value
        self.assertEqual(raw.activity_domain_count, 2)
        self.assertEqual(projected.activity_domain_count, 1)

    def test_graph_selectors_cannot_claim_to_filter_lost_source_evidence(self):
        source = graph(ab())
        for kwargs in ({"object_types": ("T",)}, {"qualifiers": ("flow",)}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    compare_ocdfgs(source, source, OCDFGComparisonSpec(**kwargs))

    def test_native_graph_count_and_evidence_contradictions_are_rejected(self):
        source = graph(ab())
        layer = source.graphs[0]
        edge = layer.edges[0]
        activity = layer.activities[0]
        bad_layers = (
            replace(layer, object_count=2),
            replace(layer, object_count=True),
            replace(layer, empty_object_ids=("t",)),
            replace(
                layer,
                activities=(replace(activity, event_occurrence_count=2),)
                + layer.activities[1:],
            ),
            replace(
                layer,
                activities=(replace(activity, event_occurrence_count=-1),)
                + layer.activities[1:],
            ),
            replace(
                layer,
                activities=(replace(activity, distinct_event_ids=()),)
                + layer.activities[1:],
            ),
            replace(layer, edges=(replace(edge, event_pair_count=2),)),
            replace(layer, edges=(replace(edge, unique_object_count=True),)),
            replace(layer, edges=(replace(edge, occurrence_count=0),)),
            replace(layer, edges=(replace(edge, target_activity="Unknown"),)),
            replace(layer, edges=(replace(edge, object_type="WrongType"),)),
            replace(layer, edges=(replace(edge, evidence=edge.evidence * 2),)),
            replace(
                layer,
                edges=(
                    replace(
                        edge,
                        evidence=(
                            replace(edge.evidence[0], object_id="MissingObject"),
                        ),
                    ),
                ),
            ),
            replace(
                layer,
                edges=(
                    replace(
                        edge,
                        evidence=(
                            replace(edge.evidence[0], source_event_id="MissingEvent"),
                        ),
                    ),
                ),
            ),
            replace(
                layer,
                edges=(
                    replace(
                        edge, evidence=(replace(edge.evidence[0], source_relations=()),)
                    ),
                ),
            ),
            replace(layer, edges=(edge, edge)),
        )
        for index, bad in enumerate(bad_layers):
            with self.subTest(case=index):
                with self.assertRaises((TypeError, ValueError)):
                    compare_ocdfgs(ObjectCentricDFG((bad,)), source)

    def test_event_ids_and_object_ids_cannot_change_types_between_layers(self):
        source = graph(log({"t": "T", "u": "U"}, (("A", ("t",)), ("B", ("u",)))))
        t, u = source.graphs
        for changed_activity in (
            replace(
                u.activities[0], distinct_event_ids=t.activities[0].distinct_event_ids
            ),
            replace(u.activities[0], object_ids=t.activities[0].object_ids),
        ):
            with self.subTest(activity=changed_activity):
                malformed = ObjectCentricDFG(
                    (t, replace(u, activities=(changed_activity,)))
                )
                with self.assertRaises(ValueError):
                    compare_ocdfgs(malformed, source)

    def test_activity_marginal_bounds_do_not_replace_actual_incidence_evidence(self):
        source = graph(
            log(
                {"one": "T", "two": "T"},
                (("A", ("one",)), ("A", ("two",)), ("B", ("one", "two"))),
            )
        )
        layer = source.graphs[0]
        a = layer.activities[0]
        self.assertEqual(a.event_occurrence_count, 2)
        self.assertEqual(len(a.distinct_event_ids), 2)
        self.assertEqual(len(a.object_ids), 2)
        # Three lies inside the loose 2 <= count <= 4 bound, but only two
        # actual (event, object) incidences occur in edges and boundaries.
        bad = replace(
            layer,
            activities=(replace(a, event_occurrence_count=3),) + layer.activities[1:],
        )
        with self.assertRaises(ValueError):
            compare_ocdfgs(ObjectCentricDFG((bad,)), source)

    def test_one_object_event_cannot_branch_to_two_direct_successors(self):
        source = graph(log({"t": "T"}, (("A", ("t",)), ("B", ("t",)), ("C", ("t",)))))
        layer = source.graphs[0]
        first, second = layer.edges
        shortcut = replace(
            first,
            target_activity="C",
            evidence=(
                replace(
                    first.evidence[0],
                    target_event_id=second.evidence[0].target_event_id,
                    target_relations=second.evidence[0].target_relations,
                ),
            ),
        )
        # All marginal memberships and counts remain plausible, but A now
        # has two immediate successors for the same object.
        bad = replace(layer, edges=layer.edges + (shortcut,))
        with self.assertRaises(ValueError):
            compare_ocdfgs(ObjectCentricDFG((bad,)), source)

    def test_disconnected_cycle_cannot_hide_behind_valid_start_and_end(self):
        source = graph(
            log(
                {"t": "T"}, (("A", ("t",)), ("B", ("t",)), ("C", ("t",)), ("D", ("t",)))
            )
        )
        layer = source.graphs[0]
        ab_edge, _, cd_edge = layer.edges
        cd_evidence = cd_edge.evidence[0]
        reverse = replace(
            cd_edge,
            source_activity="D",
            target_activity="C",
            evidence=(
                replace(
                    cd_evidence,
                    source_event_id=cd_evidence.target_event_id,
                    target_event_id=cd_evidence.source_event_id,
                    source_relations=cd_evidence.target_relations,
                    target_relations=cd_evidence.source_relations,
                ),
            ),
        )
        end_at_b = replace(
            layer.ends[0],
            activity="B",
            evidence=(
                replace(
                    layer.ends[0].evidence[0],
                    event_id=ab_edge.evidence[0].target_event_id,
                ),
            ),
        )
        # One object has valid-looking A->B boundaries plus an unreachable
        # C->D->C component. Counts alone cannot establish a lifecycle.
        bad = replace(layer, edges=(ab_edge, cd_edge, reverse), ends=(end_at_b,))
        with self.assertRaises(ValueError):
            compare_ocdfgs(ObjectCentricDFG((bad,)), source)

    def test_bad_numeric_parameters_rejected_before_calculation(self):
        for name in (
            "activity_threshold",
            "flow_threshold",
            "activity_structure_weight",
            "flow_structure_weight",
            "activity_measure_weight",
            "flow_measure_weight",
            "object_type_weight",
        ):
            for value in (-1, float("inf"), float("-inf"), float("nan"), True, "1"):
                with self.subTest(name=name, value=value):
                    with self.assertRaises((TypeError, ValueError)):
                        OCDFGComparisonSpec(**{name: value})

    def test_reference_profile_cannot_silently_select_other_measures(self):
        for kwargs in (
            {"activity_measure": "objects"},
            {"flow_measure": "occurrences"},
            {"object_type_weight": 1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    OCDFGComparisonSpec(profile="reference_untyped", **kwargs)

    def test_invalid_spec_enums_and_mutable_selectors_rejected(self):
        for kwargs in (
            {"profile": "other"},
            {"activity_measure": "other"},
            {"flow_measure": "other"},
            {"tie_policy": "guess"},
            {"zero_domain": "zero"},
            {"object_types": ["T"]},
            {"object_types": ("T", "T")},
            {"qualifiers": ["flow"]},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((TypeError, ValueError)):
                    OCDFGComparisonSpec(**kwargs)

    def test_nonnegative_weighted_scores_remain_bounded(self):
        logs = (
            log({}, ()),
            log({}, (("A", ()),)),
            ab(),
            log({"u": "U"}, (("C", ("u",)),)),
        )
        for real in logs:
            for normative in logs:
                for profile in ("typed_symmetric", "reference_untyped"):
                    with self.subTest(real=real, normative=normative, profile=profile):
                        result = compare_ocdfgs(
                            real,
                            normative,
                            OCDFGComparisonSpec(
                                profile=profile,
                                activity_structure_weight=0.2,
                                flow_structure_weight=10,
                                activity_measure_weight=0.3,
                                flow_measure_weight=2,
                            ),
                        )
                        score = fraction(result.value.score)
                        self.assertTrue(
                            score is None or Fraction(0) <= score <= Fraction(1)
                        )

    def test_materially_different_graph_inputs_have_different_identity(self):
        source = graph(ab())
        different = graph(log({"t": "T"}, (("B", ("t",)), ("A", ("t",)))))
        first = compare_ocdfgs(source, source)
        second = compare_ocdfgs(source, different)
        self.assertNotEqual(first.source_digest, second.source_digest)
        self.assertNotEqual(first.computation_id, second.computation_id)
        self.assertNotEqual(first.spec.normative_digest, second.spec.normative_digest)
        self.assertNotEqual(first.value.normative, second.value.normative)

    def test_actual_result_whitelist_roundtrip_and_file_publication(self):
        result = compare_ocdfgs(ab(), log({"t": "T"}, (("A", ("t",)),)))
        restored = persistence.result_from_json(persistence.result_json_bytes(result))
        self.assertEqual(restored, result)
        self.assertEqual(fraction(restored.value.score), Fraction(3, 7))
        with TemporaryDirectory() as temp:
            destination = Path(temp) / "comparison.json"
            persistence.write_result(result, destination)
            self.assertEqual(persistence.read_result(destination), result)


if __name__ == "__main__":
    unittest.main()
