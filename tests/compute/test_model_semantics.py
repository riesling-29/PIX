"""Native model semantics checked against hand-worked token/binding examples.

These fixtures test behavioral laws without PM4Py/OCPA or discovery output.
"""

import unittest
from dataclasses import FrozenInstanceError, replace

from pix.compute.model_semantics import (
    enabled_transitions,
    fire,
    fire_binding,
    is_binding_enabled,
    is_enabled,
    is_final,
    is_object_final,
    model_digest,
)
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

INVALID = (TypeError, ValueError)


def marking(**counts):
    return Marking(tuple(counts.items()))


def object_marking(*pairs):
    return ObjectMarking(tuple(ObjectToken(place, obj) for place, obj in pairs))


def sequential_net():
    return PetriNet(
        places=(Place("start"), Place("middle"), Place("end")),
        transitions=(Transition("a", "A"), Transition("b", "B")),
        arcs=(
            Arc("start", "a"),
            Arc("a", "middle"),
            Arc("middle", "b"),
            Arc("b", "end"),
        ),
        initial_marking=marking(start=1),
        final_marking=marking(end=1),
    )


def shipping_net(*, variable=False, min_objects=1, max_objects=None):
    """An order and one/many items must participate in the same firing."""
    return ObjectCentricPetriNet(
        places=(
            TypedPlace("order_ready", "order"),
            TypedPlace("order_done", "order"),
            TypedPlace("item_ready", "item"),
            TypedPlace("item_done", "item"),
        ),
        transitions=(Transition("ship", "Ship"),),
        arcs=(
            ObjectArc("order_ready", "ship"),
            ObjectArc("ship", "order_done"),
            ObjectArc("item_ready", "ship", variable, min_objects, max_objects),
            ObjectArc("ship", "item_done", variable, min_objects, max_objects),
        ),
        objects=(("o1", "order"), ("i1", "item"), ("i2", "item")),
        initial_marking=object_marking(
            ("order_ready", "o1"), ("item_ready", "i1"), ("item_ready", "i2")
        ),
        final_marking=object_marking(
            ("order_done", "o1"), ("item_done", "i1"), ("item_done", "i2")
        ),
    )


class TestPetriNetBehavior(unittest.TestCase):
    def test_sequence_and_exact_final_marking(self):
        net = sequential_net()
        self.assertEqual(enabled_transitions(net, net.initial_marking), ("a",))
        middle = fire(net, net.initial_marking, "a")
        self.assertEqual(middle, marking(middle=1))
        self.assertFalse(is_final(net, middle))
        self.assertEqual(enabled_transitions(net, middle), ("b",))
        end = fire(net, middle, "b")
        self.assertEqual(end, marking(end=1))
        self.assertTrue(is_final(net, end))
        self.assertEqual(enabled_transitions(net, end), ())
        self.assertFalse(is_final(net, marking(end=1, start=1)))
        self.assertFalse(is_final(net, Marking()))

    def test_choice_consumes_shared_token(self):
        net = PetriNet(
            (Place("p"), Place("left"), Place("right")),
            (Transition("b", "B"), Transition("a", "A")),
            (Arc("p", "a"), Arc("a", "left"), Arc("p", "b"), Arc("b", "right")),
            marking(p=1),
            marking(left=1),
        )
        self.assertEqual(enabled_transitions(net, net.initial_marking), ("a", "b"))
        left = fire(net, net.initial_marking, "a")
        self.assertFalse(is_enabled(net, left, "b"))
        self.assertEqual(left, marking(left=1))

    def test_and_join_waits_for_both_parallel_branches(self):
        net = PetriNet(
            tuple(Place(name) for name in ("p", "l", "r", "ld", "rd", "end")),
            (
                Transition("split"),
                Transition("left", "L"),
                Transition("right", "R"),
                Transition("join"),
            ),
            (
                Arc("p", "split"),
                Arc("split", "l"),
                Arc("split", "r"),
                Arc("l", "left"),
                Arc("left", "ld"),
                Arc("r", "right"),
                Arc("right", "rd"),
                Arc("ld", "join"),
                Arc("rd", "join"),
                Arc("join", "end"),
            ),
            marking(p=1),
            marking(end=1),
        )
        split = fire(net, net.initial_marking, "split")
        self.assertEqual(split, marking(l=1, r=1))
        self.assertEqual(enabled_transitions(net, split), ("left", "right"))
        left_first = fire(net, split, "left")
        self.assertFalse(is_enabled(net, left_first, "join"))
        both = fire(net, left_first, "right")
        right_first = fire(net, fire(net, split, "right"), "left")
        self.assertEqual(both, right_first)
        self.assertTrue(is_final(net, fire(net, both, "join")))

    def test_silent_loop_and_visible_exit_have_distinct_identity(self):
        net = PetriNet(
            (Place("p"), Place("end")),
            (Transition("loop"), Transition("exit", "Done")),
            (Arc("p", "loop"), Arc("loop", "p"), Arc("p", "exit"), Arc("exit", "end")),
            marking(p=1),
            marking(end=1),
        )
        after_loop = fire(net, net.initial_marking, "loop")
        self.assertEqual(after_loop, net.initial_marking)
        self.assertTrue(is_final(net, fire(net, after_loop, "exit")))

    def test_source_and_sink_transitions_follow_empty_incidence(self):
        net = PetriNet(
            (Place("p"),),
            (Transition("create", "Create"), Transition("consume", "Consume")),
            (Arc("create", "p"), Arc("p", "consume")),
            Marking(),
            Marking(),
        )
        self.assertEqual(enabled_transitions(net, Marking()), ("create",))
        first = fire(net, Marking(), "create")
        second = fire(net, first, "create")
        self.assertEqual(second, marking(p=2))
        self.assertTrue(
            is_final(net, fire(net, fire(net, second, "consume"), "consume"))
        )

    def test_equal_activity_labels_do_not_merge_transitions(self):
        net = replace(
            sequential_net(),
            transitions=(Transition("a", "Approve"), Transition("b", "Approve")),
        )
        self.assertEqual(enabled_transitions(net, net.initial_marking), ("a",))
        self.assertEqual(
            enabled_transitions(net, fire(net, net.initial_marking, "a")), ("b",)
        )

    def test_weighted_arcs_consume_and_produce_exact_counts(self):
        net = PetriNet(
            (Place("p"), Place("q")),
            (Transition("t", "Batch"),),
            (Arc("p", "t", 2), Arc("t", "q", 3)),
            marking(p=3, q=1),
            marking(p=1, q=4),
        )
        self.assertFalse(is_enabled(net, marking(p=1), "t"))
        result = fire(net, net.initial_marking, "t")
        self.assertEqual(result, marking(p=1, q=4))
        self.assertTrue(is_final(net, result))

    def test_disabled_and_unknown_firing_leave_input_unchanged(self):
        net = sequential_net()
        before = net.initial_marking
        for transition in ("b", "missing"):
            with self.subTest(transition=transition):
                with self.assertRaises(ValueError):
                    fire(net, before, transition)
                self.assertEqual(before, marking(start=1))

    def test_unknown_place_is_invalid_marking_not_missing_token(self):
        net = sequential_net()
        for operation in (
            lambda: enabled_transitions(net, marking(unknown=1)),
            lambda: is_enabled(net, marking(unknown=1), "a"),
            lambda: fire(net, marking(unknown=1), "a"),
            lambda: is_final(net, marking(unknown=1)),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()


class TestModelContracts(unittest.TestCase):
    def test_contracts_are_frozen(self):
        net = sequential_net()
        with self.assertRaises(FrozenInstanceError):
            net.places = ()
        with self.assertRaises(FrozenInstanceError):
            net.initial_marking.tokens = ()

    def test_silent_is_none_and_empty_activity_rejected(self):
        self.assertIsNone(Transition("silent").activity)
        with self.assertRaises(INVALID):
            Transition("t", "")

    def test_empty_ids_and_invalid_weights_rejected(self):
        constructors = (
            lambda: Place(""),
            lambda: Transition(""),
            lambda: TypedPlace("", "order"),
            lambda: TypedPlace("p", ""),
        )
        for construct in constructors:
            with self.subTest(construct=construct):
                with self.assertRaises(INVALID):
                    construct()
        for weight in (0, -1, True, 1.5, "1"):
            with self.subTest(weight=weight):
                with self.assertRaises(INVALID):
                    Arc("p", "t", weight)

    def test_invalid_token_counts_rejected(self):
        for count in (-1, True, 1.5, "1"):
            with self.subTest(count=count):
                with self.assertRaises(INVALID):
                    Marking((("p", count),))

    def test_duplicate_ids_including_cross_kind_rejected(self):
        net = sequential_net()
        for change in (
            {"places": net.places + (Place("start"),)},
            {"transitions": net.transitions + (Transition("a", "Other"),)},
            {"places": net.places + (Place("a"),)},
        ):
            with self.subTest(change=change):
                with self.assertRaises(INVALID):
                    replace(net, **change)

    def test_invalid_incidence_is_rejected(self):
        net = sequential_net()
        for invalid in (
            Arc("start", "missing"),
            Arc("start", "end"),
            Arc("a", "b"),
            Arc("start", "a"),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(INVALID):
                    replace(net, arcs=net.arcs + (invalid,))

    def test_initial_and_final_markings_must_use_known_places(self):
        net = sequential_net()
        for field in ("initial_marking", "final_marking"):
            with self.subTest(field=field):
                with self.assertRaises(INVALID):
                    replace(net, **{field: marking(missing=1)})

    def test_model_digest_is_independent_of_declaration_order(self):
        net = sequential_net()
        reordered = replace(
            net,
            places=net.places[::-1],
            transitions=net.transitions[::-1],
            arcs=net.arcs[::-1],
        )
        self.assertEqual(net, reordered)
        self.assertIsInstance(model_digest(net), str)
        self.assertEqual(model_digest(net), model_digest(reordered))

    def test_model_digest_distinguishes_label_weight_and_marking(self):
        net = sequential_net()
        changes = (
            replace(
                net, transitions=(Transition("a", "Different"), Transition("b", "B"))
            ),
            replace(
                net,
                arcs=tuple(
                    replace(a, weight=2) if a.source == "start" else a for a in net.arcs
                ),
            ),
            replace(net, initial_marking=marking(start=2)),
            replace(net, final_marking=marking(end=2)),
        )
        for altered in changes:
            with self.subTest(altered=altered):
                self.assertNotEqual(model_digest(net), model_digest(altered))


class TestObjectCentricBindings(unittest.TestCase):
    def test_fixed_binding_fires_exactly_selected_objects(self):
        net = shipping_net()
        selected = Binding("ship", (("order", ("o1",)), ("item", ("i1",))))
        self.assertTrue(is_binding_enabled(net, net.initial_marking, selected))
        after = fire_binding(net, net.initial_marking, selected)
        self.assertEqual(
            after,
            object_marking(
                ("order_done", "o1"), ("item_done", "i1"), ("item_ready", "i2")
            ),
        )
        self.assertFalse(is_object_final(net, after))

    def test_variable_binding_consumes_multiple_objects_jointly(self):
        net = shipping_net(variable=True, min_objects=1, max_objects=2)
        selected = Binding("ship", (("item", ("i2", "i1")), ("order", ("o1",))))
        self.assertTrue(is_binding_enabled(net, net.initial_marking, selected))
        after = fire_binding(net, net.initial_marking, selected)
        self.assertTrue(is_object_final(net, after))
        self.assertFalse(is_binding_enabled(net, after, selected))

    def test_fixed_cardinality_does_not_accept_two_objects(self):
        net = shipping_net()
        selected = Binding("ship", (("order", ("o1",)), ("item", ("i1", "i2"))))
        self.assertFalse(is_binding_enabled(net, net.initial_marking, selected))
        with self.assertRaises(ValueError):
            fire_binding(net, net.initial_marking, selected)

    def test_variable_bounds_apply_to_selected_set(self):
        net = shipping_net(variable=True, min_objects=2, max_objects=2)
        selected = Binding("ship", (("order", ("o1",)), ("item", ("i1",))))
        self.assertFalse(is_binding_enabled(net, net.initial_marking, selected))

    def test_every_input_place_needs_the_same_concrete_selected_object(self):
        net = ObjectCentricPetriNet(
            (
                TypedPlace("p", "order"),
                TypedPlace("q", "order"),
                TypedPlace("done", "order"),
            ),
            (Transition("join", "Join"),),
            (ObjectArc("p", "join"), ObjectArc("q", "join"), ObjectArc("join", "done")),
            object_marking(("p", "o1"), ("q", "o2")),
            object_marking(("done", "o1")),
            (("o1", "order"), ("o2", "order")),
        )
        selected = Binding("join", (("order", ("o1",)),))
        # The typewise token count is sufficient, but this joint binding is not.
        self.assertFalse(is_binding_enabled(net, net.initial_marking, selected))
        complete = object_marking(("p", "o1"), ("q", "o1"), ("q", "o2"))
        self.assertTrue(is_binding_enabled(net, complete, selected))
        self.assertEqual(
            fire_binding(net, complete, selected),
            object_marking(("done", "o1"), ("q", "o2")),
        )

    def test_mixed_arc_policies_for_one_transition_and_type_rejected(self):
        net = shipping_net(variable=True, min_objects=1, max_objects=2)
        for replacement_arc in (
            ObjectArc("ship", "item_done"),
            ObjectArc("ship", "item_done", True, 1, 3),
            ObjectArc("ship", "item_done", True, 0, 2),
        ):
            with self.subTest(replacement_arc=replacement_arc):
                with self.assertRaises(INVALID):
                    replace(
                        net,
                        arcs=tuple(
                            replacement_arc
                            if a.source == "ship" and a.target == "item_done"
                            else a
                            for a in net.arcs
                        ),
                    )

    def test_optional_object_set_only_when_all_its_arcs_allow_zero(self):
        net = shipping_net(variable=True, min_objects=0, max_objects=2)
        empty_items = Binding("ship", (("order", ("o1",)), ("item", ())))
        self.assertTrue(is_binding_enabled(net, net.initial_marking, empty_items))
        self.assertEqual(
            fire_binding(net, net.initial_marking, empty_items),
            object_marking(
                ("order_done", "o1"), ("item_ready", "i1"), ("item_ready", "i2")
            ),
        )
        required = shipping_net(variable=True, min_objects=1, max_objects=2)
        self.assertFalse(
            is_binding_enabled(required, required.initial_marking, empty_items)
        )

    def test_missing_extra_unknown_and_wrong_type_binding_rejected(self):
        net = shipping_net()
        bindings = (
            Binding("ship", (("order", ("o1",)),)),
            Binding("ship", (("order", ("o1",)), ("item", ("i1",)), ("resource", ()))),
            Binding("ship", (("order", ("missing",)), ("item", ("i1",)))),
            Binding("ship", (("order", ("i2",)), ("item", ("i1",)))),
            Binding("missing", (("order", ("o1",)), ("item", ("i1",)))),
        )
        for selected in bindings:
            with self.subTest(selected=selected):
                self.assertFalse(is_binding_enabled(net, net.initial_marking, selected))
                with self.assertRaises(ValueError):
                    fire_binding(net, net.initial_marking, selected)

    def test_same_object_token_multiplicity_is_preserved(self):
        net = shipping_net()
        duplicate = object_marking(
            ("order_ready", "o1"), ("order_ready", "o1"), ("item_ready", "i1")
        )
        selected = Binding("ship", (("order", ("o1",)), ("item", ("i1",))))
        after = fire_binding(net, duplicate, selected)
        self.assertEqual(
            after,
            object_marking(
                ("order_ready", "o1"), ("order_done", "o1"), ("item_done", "i1")
            ),
        )
        self.assertEqual(len(duplicate.tokens), 3)

    def test_invalid_marking_raises_instead_of_appearing_disabled(self):
        net = shipping_net()
        selected = Binding("ship", (("order", ("o1",)), ("item", ("i1",))))
        invalid = (
            object_marking(("unknown", "o1")),
            object_marking(("order_ready", "unknown")),
            object_marking(("order_ready", "i1")),
        )
        for current in invalid:
            with self.subTest(current=current):
                for operation in (
                    lambda: is_binding_enabled(net, current, selected),
                    lambda: fire_binding(net, current, selected),
                    lambda: is_object_final(net, current),
                ):
                    with self.assertRaises(ValueError):
                        operation()

    def test_final_object_marking_requires_exact_identity_and_multiplicity(self):
        net = shipping_net()
        self.assertTrue(is_object_final(net, net.final_marking))
        self.assertFalse(is_object_final(net, ObjectMarking()))
        surplus = ObjectMarking(
            net.final_marking.tokens + (ObjectToken("order_done", "o1"),)
        )
        self.assertFalse(is_object_final(net, surplus))
        missing = object_marking(("order_done", "o1"), ("item_done", "i1"))
        self.assertFalse(is_object_final(net, missing))

    def test_disabled_firing_does_not_modify_object_marking(self):
        net = shipping_net()
        current = object_marking(("order_ready", "o1"))
        selected = Binding("ship", (("order", ("o1",)), ("item", ("i1",))))
        with self.assertRaises(ValueError):
            fire_binding(net, current, selected)
        self.assertEqual(current, object_marking(("order_ready", "o1")))

    def test_object_silent_self_loop_restores_same_token_multiset(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "order"),),
            (Transition("tau"),),
            (ObjectArc("p", "tau"), ObjectArc("tau", "p")),
            object_marking(("p", "o1"), ("p", "o1")),
            object_marking(("p", "o1"), ("p", "o1")),
            (("o1", "order"),),
        )
        selected = Binding("tau", (("order", ("o1",)),))
        self.assertTrue(is_binding_enabled(net, net.initial_marking, selected))
        self.assertEqual(
            fire_binding(net, net.initial_marking, selected), net.initial_marking
        )

    def test_object_source_and_sink_affect_tokens_not_object_registry(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "order"),),
            (Transition("create", "Create"), Transition("consume", "Consume")),
            (ObjectArc("create", "p"), ObjectArc("p", "consume")),
            ObjectMarking(),
            ObjectMarking(),
            (("o1", "order"),),
        )
        create = Binding("create", (("order", ("o1",)),))
        consume = Binding("consume", (("order", ("o1",)),))
        created = fire_binding(net, net.initial_marking, create)
        self.assertEqual(created, object_marking(("p", "o1")))
        self.assertTrue(is_object_final(net, fire_binding(net, created, consume)))
        undeclared = Binding("create", (("order", ("new_object",)),))
        self.assertFalse(is_binding_enabled(net, net.initial_marking, undeclared))


class TestObjectModelContracts(unittest.TestCase):
    def test_duplicate_binding_ids_and_types_rejected(self):
        for objects in (
            (("order", ("o1", "o1")),),
            (("order", ("o1",)), ("order", ("o2",))),
            (("order", ("same",)), ("item", ("same",))),
        ):
            with self.subTest(objects=objects):
                with self.assertRaises(INVALID):
                    Binding("ship", objects)

    def test_invalid_object_arc_bounds_rejected(self):
        for kwargs in (
            {"variable": "yes"},
            {"variable": True, "min_objects": -1},
            {"variable": True, "min_objects": True},
            {"variable": True, "min_objects": 2, "max_objects": 1},
            {"variable": True, "max_objects": 1.5},
            {"variable": True, "max_objects": True},
            {"variable": False, "min_objects": 0},
            {"variable": False, "max_objects": 2},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(INVALID):
                    ObjectArc("p", "t", **kwargs)

    def test_invalid_object_registry_and_initial_marking_rejected(self):
        net = shipping_net()
        changes = (
            {"objects": net.objects + (("o1", "order"),)},
            {"initial_marking": object_marking(("missing", "o1"))},
            {"initial_marking": object_marking(("order_ready", "missing"))},
            {"initial_marking": object_marking(("order_ready", "i1"))},
        )
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(INVALID):
                    replace(net, **change)

    def test_object_net_invalid_incidence_rejected(self):
        net = shipping_net()
        for arc in (
            ObjectArc("order_ready", "missing"),
            ObjectArc("order_ready", "item_ready"),
            ObjectArc("ship", "ship"),
            ObjectArc("order_ready", "ship"),
        ):
            with self.subTest(arc=arc):
                with self.assertRaises(INVALID):
                    replace(net, arcs=net.arcs + (arc,))

    def test_order_independent_object_model_and_binding(self):
        net = shipping_net(variable=True, max_objects=2)
        reordered = replace(
            net,
            places=net.places[::-1],
            transitions=net.transitions[::-1],
            arcs=net.arcs[::-1],
            objects=net.objects[::-1],
            initial_marking=ObjectMarking(net.initial_marking.tokens[::-1]),
            final_marking=ObjectMarking(net.final_marking.tokens[::-1]),
        )
        self.assertEqual(net, reordered)
        self.assertEqual(model_digest(net), model_digest(reordered))
        self.assertEqual(
            Binding("ship", (("order", ("o1",)), ("item", ("i2", "i1")))),
            Binding("ship", (("item", ("i1", "i2")), ("order", ("o1",)))),
        )

    def test_object_digest_distinguishes_arc_constraint_and_object_identity(self):
        net = shipping_net(variable=True, max_objects=2)
        altered_arc = replace(
            net,
            arcs=tuple(
                replace(a, max_objects=3) if a.variable else a for a in net.arcs
            ),
        )
        altered_registry = replace(net, objects=net.objects + (("i3", "item"),))
        self.assertNotEqual(model_digest(net), model_digest(altered_arc))
        self.assertNotEqual(model_digest(net), model_digest(altered_registry))


if __name__ == "__main__":
    unittest.main()
