"""Finite binding completeness, joint-object availability, and cap boundaries."""

import random
import unittest
from dataclasses import FrozenInstanceError, replace
from itertools import combinations, product

from pix.compute.model_semantics import fire_binding, is_binding_enabled
from pix.compute.object_bindings import (
    enumerate_enabled_bindings,
    transition_binding_types,
)
from pix.contracts.models import (
    Binding,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)


def marking(*pairs):
    return ObjectMarking(tuple(ObjectToken(*pair) for pair in pairs))


def single_type(*, variable=False, minimum=1, maximum=None, source=False):
    return ObjectCentricPetriNet(
        (TypedPlace("p", "T"), TypedPlace("q", "T")),
        (Transition("t", "A"),),
        (ObjectArc("t", "q", variable, minimum, maximum),)
        if source
        else (
            ObjectArc("p", "t", variable, minimum, maximum),
            ObjectArc("t", "q", variable, minimum, maximum),
        ),
        marking(("p", "a"), ("p", "b"), ("p", "c")),
        ObjectMarking(),
        (("a", "T"), ("b", "T"), ("c", "T")),
    )


def selections(result):
    return tuple(binding.objects for binding in result.bindings)


class TestFiniteObjectBindings(unittest.TestCase):
    def test_fixed_objects_each_generate_one_binding(self):
        net = single_type()
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=10)
        self.assertEqual(
            selections(result),
            ((("T", ("a",)),), (("T", ("b",)),), (("T", ("c",)),)),
        )
        self.assertEqual(result.candidate_count, 3)
        self.assertTrue(result.complete)
        for binding in result.bindings:
            self.assertTrue(is_binding_enabled(net, net.initial_marking, binding))

    def test_variable_cardinality_then_lexicographic_order(self):
        net = single_type(variable=True, minimum=1, maximum=2)
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=6)
        self.assertEqual(
            [binding.objects[0][1] for binding in result.bindings],
            [("a",), ("b",), ("c",), ("a", "b"), ("a", "c"), ("b", "c")],
        )
        self.assertEqual(result.candidate_count, 6)
        self.assertTrue(result.complete)

    def test_joint_binding_requires_same_object_at_every_input(self):
        net = single_type()
        net = replace(
            net,
            places=net.places + (TypedPlace("r", "T"),),
            arcs=net.arcs + (ObjectArc("r", "t"),),
        )
        different_objects = marking(("p", "a"), ("r", "b"))
        result = enumerate_enabled_bindings(net, different_objects, max_bindings=10)
        self.assertEqual(result.bindings, ())
        self.assertEqual(result.candidate_count, 0)
        self.assertTrue(result.complete)
        common = marking(("p", "a"), ("p", "b"), ("r", "b"), ("r", "c"))
        result = enumerate_enabled_bindings(net, common, max_bindings=10)
        self.assertEqual(result.bindings, (Binding("t", (("T", ("b",)),)),))

    def test_repeated_tokens_neither_duplicate_bindings_nor_raise_cardinality(self):
        net = single_type()
        repeated = marking(("p", "a"), ("p", "a"), ("p", "a"))
        result = enumerate_enabled_bindings(net, repeated, max_bindings=10)
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(result.bindings, (Binding("t", (("T", ("a",)),)),))
        self.assertEqual(
            fire_binding(net, repeated, result.bindings[0]),
            marking(("p", "a"), ("p", "a"), ("q", "a")),
        )
        two_required = single_type(variable=True, minimum=2)
        result = enumerate_enabled_bindings(two_required, repeated, max_bindings=10)
        self.assertEqual(result.candidate_count, 0)

    def test_empty_selection_keeps_type_key_and_needs_explicit_zero_bound(self):
        net = single_type(variable=True, minimum=0)
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=10)
        self.assertEqual(result.bindings, (Binding("t", (("T", ()),)),))
        self.assertEqual(result.candidate_count, 1)
        self.assertTrue(is_binding_enabled(net, ObjectMarking(), result.bindings[0]))
        required = single_type(variable=True, minimum=1)
        result = enumerate_enabled_bindings(required, ObjectMarking(), max_bindings=10)
        self.assertEqual(result.bindings, ())

    def test_optional_type_without_declared_objects(self):
        net = single_type(variable=True, minimum=0, source=True)
        net = replace(net, objects=(), initial_marking=ObjectMarking())
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=1)
        self.assertEqual(result.bindings, (Binding("t", (("T", ()),)),))
        required = replace(net, arcs=(ObjectArc("t", "q"),))
        result = enumerate_enabled_bindings(required, ObjectMarking(), max_bindings=1)
        self.assertEqual(result.candidate_count, 0)

    def test_zero_maximum_permits_only_empty_set(self):
        net = single_type(variable=True, minimum=0, maximum=0)
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=100)
        self.assertEqual(result.bindings, (Binding("t", (("T", ()),)),))
        self.assertEqual(result.candidate_count, 1)

    def test_types_combine_jointly_and_missing_required_type_disables(self):
        net = single_type()
        net = replace(
            net,
            places=net.places + (TypedPlace("rp", "R"),),
            arcs=net.arcs + (ObjectArc("rp", "t"),),
            objects=net.objects + (("r1", "R"), ("r2", "R")),
        )
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=10)
        self.assertEqual(result.candidate_count, 0)
        current = marking(("p", "a"), ("p", "b"), ("rp", "r1"), ("rp", "r2"))
        result = enumerate_enabled_bindings(net, current, max_bindings=10)
        self.assertEqual(
            selections(result),
            (
                (("R", ("r1",)), ("T", ("a",))),
                (("R", ("r1",)), ("T", ("b",))),
                (("R", ("r2",)), ("T", ("a",))),
                (("R", ("r2",)), ("T", ("b",))),
            ),
        )
        self.assertEqual(result.candidate_count, 4)

    def test_source_draws_only_from_declared_objects_not_current_tokens(self):
        net = single_type(source=True)
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=10)
        self.assertEqual(result.candidate_count, 3)
        self.assertEqual(
            {
                obj
                for binding in result.bindings
                for _, ids in binding.objects
                for obj in ids
            },
            {"a", "b", "c"},
        )
        after = fire_binding(net, ObjectMarking(), result.bindings[0])
        repeated = enumerate_enabled_bindings(net, after, max_bindings=10)
        self.assertEqual(result, repeated)
        self.assertEqual(net.objects, (("a", "T"), ("b", "T"), ("c", "T")))

    def test_mixed_input_type_and_source_only_type(self):
        net = single_type()
        net = replace(
            net,
            places=net.places + (TypedPlace("out", "S"),),
            arcs=net.arcs + (ObjectArc("t", "out"),),
            objects=net.objects + (("s1", "S"), ("s2", "S")),
        )
        current = marking(("p", "b"))
        result = enumerate_enabled_bindings(net, current, max_bindings=10)
        self.assertEqual(
            selections(result),
            ((("S", ("s1",)), ("T", ("b",))), (("S", ("s2",)), ("T", ("b",)))),
        )

    def test_sink_and_no_arc_transitions_have_finite_bindings(self):
        net = single_type()
        net = replace(
            net,
            transitions=(Transition("t", "A"), Transition("empty", "A")),
            arcs=(ObjectArc("p", "t"),),
        )
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=10)
        self.assertEqual(result.candidate_count, 4)
        self.assertEqual(result.bindings[0], Binding("empty", ()))
        self.assertEqual(
            tuple(b.transition_id for b in result.bindings), ("empty", "t", "t", "t")
        )
        self.assertEqual(
            fire_binding(net, ObjectMarking(), result.bindings[0]), ObjectMarking()
        )

    def test_output_tokens_do_not_restrict_availability_or_capacity(self):
        net = single_type()
        current = marking(("p", "a"), ("q", "a"), ("q", "a"))
        result = enumerate_enabled_bindings(net, current, max_bindings=10)
        self.assertEqual(result.bindings, (Binding("t", (("T", ("a",)),)),))
        self.assertEqual(
            fire_binding(net, current, result.bindings[0]),
            marking(("q", "a"), ("q", "a"), ("q", "a")),
        )

    def test_cap_is_global_exact_at_boundary_and_count_is_not_truncated(self):
        net = single_type()
        net = replace(net, transitions=net.transitions + (Transition("z"),))
        full = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=100)
        self.assertEqual(full.candidate_count, 4)
        for cap in range(6):
            with self.subTest(cap=cap):
                result = enumerate_enabled_bindings(
                    net, net.initial_marking, max_bindings=cap
                )
                self.assertEqual(result.bindings, full.bindings[:cap])
                self.assertEqual(result.candidate_count, 4)
                self.assertEqual(result.complete, cap >= 4)

    def test_later_disabled_transition_does_not_make_exact_cap_incomplete(self):
        net = single_type()
        net = replace(
            net,
            transitions=net.transitions + (Transition("z"),),
            arcs=net.arcs + (ObjectArc("q", "z"),),
        )
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=3)
        self.assertTrue(result.complete)
        self.assertEqual(result.candidate_count, 3)

    def test_zero_cap_on_dead_marking_is_complete(self):
        net = single_type()
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=0)
        self.assertTrue(result.complete)
        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.bindings, ())

    def test_arbitrarily_large_cap_on_small_universe(self):
        net = single_type()
        result = enumerate_enabled_bindings(
            net, net.initial_marking, max_bindings=10**30
        )
        self.assertTrue(result.complete)
        self.assertEqual(result.candidate_count, 3)
        self.assertEqual(len(result.bindings), 3)

    def test_unbounded_and_large_maxima_clamp_to_finite_universe(self):
        for maximum in (None, 10**30):
            with self.subTest(maximum=maximum):
                net = single_type(variable=True, minimum=0, maximum=maximum)
                result = enumerate_enabled_bindings(
                    net, net.initial_marking, max_bindings=100
                )
                self.assertTrue(result.complete)
                self.assertEqual(result.candidate_count, 8)
        net = single_type(variable=True, minimum=4)
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=100)
        self.assertEqual(result.candidate_count, 0)

    def test_large_two_type_powerset_is_counted_without_materialization(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "A"), TypedPlace("q", "B")),
            (Transition("t"),),
            (ObjectArc("t", "p", True, 0), ObjectArc("t", "q", True, 0)),
            ObjectMarking(),
            ObjectMarking(),
            tuple(
                (f"{kind}{index:03}", kind)
                for kind in ("A", "B")
                for index in range(80)
            ),
        )
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=2)
        self.assertEqual(result.candidate_count, 2**160)
        self.assertFalse(result.complete)
        self.assertEqual(
            result.bindings,
            (
                Binding("t", (("A", ()), ("B", ()))),
                Binding("t", (("A", ()), ("B", ("B000",)))),
            ),
        )

    def test_many_types_do_not_depend_on_python_recursion_limit(self):
        types = tuple(f"T{index:04}" for index in range(1200))
        net = ObjectCentricPetriNet(
            tuple(TypedPlace(f"p{kind}", kind) for kind in types),
            (Transition("t"),),
            tuple(ObjectArc("t", f"p{kind}", True, 0, 0) for kind in types),
            ObjectMarking(),
            ObjectMarking(),
            (),
        )
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=1)
        self.assertTrue(result.complete)
        self.assertEqual(result.candidate_count, 1)
        self.assertEqual(
            result.bindings[0].objects, tuple((kind, ()) for kind in types)
        )

    def test_types_helper_retains_optional_keys_and_validates_transition(self):
        net = single_type(variable=True, minimum=0)
        net = replace(net, transitions=net.transitions + (Transition("empty"),))
        self.assertEqual(transition_binding_types(net, "t"), ("T",))
        self.assertEqual(transition_binding_types(net, "empty"), ())
        with self.assertRaises(ValueError):
            transition_binding_types(net, "unknown")
        with self.assertRaises(TypeError):
            transition_binding_types(net, None)
        with self.assertRaises(TypeError):
            transition_binding_types(None, "t")

    def test_invalid_net_marking_and_cap_raise(self):
        net = single_type()
        for cap in (None, True, 1.5, "1", -1):
            with self.subTest(cap=cap):
                with self.assertRaises((TypeError, ValueError)):
                    enumerate_enabled_bindings(
                        net, net.initial_marking, max_bindings=cap
                    )
        for current in (
            None,
            marking(("unknown", "a")),
            marking(("p", "undeclared")),
        ):
            with self.subTest(current=current):
                with self.assertRaises((TypeError, ValueError)):
                    enumerate_enabled_bindings(net, current, max_bindings=1)
        with self.assertRaises(TypeError):
            enumerate_enabled_bindings(None, ObjectMarking(), max_bindings=1)

    def test_result_is_immutable(self):
        net = single_type()
        result = enumerate_enabled_bindings(net, net.initial_marking, max_bindings=1)
        with self.assertRaises(FrozenInstanceError):
            result.complete = True

    def test_empty_model_has_no_bindings(self):
        net = ObjectCentricPetriNet((), (), (), ObjectMarking(), ObjectMarking(), ())
        result = enumerate_enabled_bindings(net, ObjectMarking(), max_bindings=1)
        self.assertTrue(result.complete)
        self.assertEqual(result.candidate_count, 0)
        self.assertEqual(result.bindings, ())


class TestTinyUniverseOracle(unittest.TestCase):
    def test_exhaustive_subsets_against_shared_firing_semantics(self):
        """Unfiltered tiny powersets independently check enumeration completeness.

        Fixed seed varies presets, source-only types, cardinality intervals and
        token multiplicity. The oracle constructs every finite candidate first
        and delegates enabledness to the separately implemented firing checker.
        """
        rng = random.Random(48219)
        objects = tuple((f"{kind}{i}", kind) for kind in ("A", "B") for i in range(3))
        places = tuple(
            TypedPlace(f"{kind}{side}", kind)
            for kind in ("A", "B")
            for side in ("p", "q", "out")
        )
        for case in range(40):
            with self.subTest(case=case):
                arcs = []
                required = {}
                for transition in ("t1", "t2"):
                    required[transition] = []
                    for kind in ("A", "B"):
                        included = tuple(rng.choice((False, True)) for _ in range(3))
                        if not any(included):
                            continue
                        required[transition].append(kind)
                        minimum = rng.randrange(4)
                        maximum = rng.choice((None, minimum, minimum + 1))
                        for side, enabled in zip(("p", "q", "out"), included):
                            if enabled:
                                source, target = (
                                    (transition, f"{kind}{side}")
                                    if side == "out"
                                    else (f"{kind}{side}", transition)
                                )
                                arcs.append(
                                    ObjectArc(source, target, True, minimum, maximum)
                                )
                current = ObjectMarking(
                    tuple(
                        ObjectToken(place.id, object_id)
                        for place in places
                        for object_id, object_type in objects
                        if object_type == place.object_type
                        for _ in range(rng.randrange(3))
                    )
                )
                net = ObjectCentricPetriNet(
                    places,
                    (Transition("t1"), Transition("t2")),
                    tuple(arcs),
                    current,
                    ObjectMarking(),
                    objects,
                )
                expected = []
                for transition in ("t1", "t2"):
                    pools = []
                    for kind in required[transition]:
                        ids = tuple(
                            obj for obj, object_type in objects if object_type == kind
                        )
                        pools.append(
                            tuple(
                                combination
                                for size in range(4)
                                for combination in combinations(ids, size)
                            )
                        )
                    for selected in product(*pools):
                        binding = Binding(
                            transition, tuple(zip(required[transition], selected))
                        )
                        if is_binding_enabled(net, current, binding):
                            expected.append(binding)
                full = enumerate_enabled_bindings(net, current, max_bindings=1000)
                self.assertEqual(full.bindings, tuple(expected))
                self.assertEqual(full.candidate_count, len(expected))
                self.assertTrue(full.complete)
                for cap in (0, 1, len(expected), len(expected) + 1):
                    limited = enumerate_enabled_bindings(net, current, max_bindings=cap)
                    self.assertEqual(limited.bindings, tuple(expected[:cap]))
                    self.assertEqual(limited.candidate_count, len(expected))
                    self.assertEqual(limited.complete, cap >= len(expected))


if __name__ == "__main__":
    unittest.main()
