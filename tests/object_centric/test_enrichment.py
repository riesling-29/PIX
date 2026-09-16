"""Hand-joined enrichment examples and persisted-plan tampering counterexamples."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.object_centric.enrichment import (
    LifecycleQualifierSpec,
    ObjectRelationEnrichmentSpec,
    enrich_object_relations,
    mark_lifecycle_qualifiers,
    materialize_enriched_ocel,
)
from pix.object_centric.relations import ObjectGraphSpec
from pix.ocel import (
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
    OCELImportInfo,
    TimezoneInfo,
    ValueType,
    canonical_digest,
    validate,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def example():
    return OCEL(
        event_types=(
            EventType("A", (Attribute("due", ValueType.TIME),)),
            EventType("Unused"),
        ),
        object_types=(
            ObjectType("Thing", (Attribute("state", ValueType.STRING),)),
            ObjectType("Unused"),
        ),
        events=tuple(
            Event(
                f"e{i}",
                "A",
                T0 + timedelta(seconds=i),
                (EventAttr("due", T0 + timedelta(days=i)),),
            )
            for i in range(1, 5)
        ),
        objects=(
            Object(
                "a",
                "Thing",
                (
                    ObjectAttr("state", "new", T0),
                    ObjectAttr("state", "done", T0 + timedelta(seconds=9)),
                ),
            ),
            Object("b", "Thing"),
            Object("c", "Thing"),
            Object("z", "Unused"),
        ),
        e2o=(
            E2O("e1", "a", "flow"),
            E2O("e2", "a", "flow"),
            E2O("e2", "a", "audit"),
            E2O("e2", "b", "flow"),
            E2O("e3", "a", "flow"),
            E2O("e3", "b", "flow"),
            E2O("e4", "c", "audit"),
        ),
        o2o=(O2O("b", "a", "original"), O2O("z", "c", "original")),
        import_info=OCELImportInfo("manual", "json", "abc", TimezoneInfo()),
    )


def triples(rows):
    return {row.relation for row in rows}


def test_graph_manual_join_deduplicates_roles_and_retains_all_source_facts():
    source = example()
    result = enrich_object_relations(source)
    assert result.status is ComputeStatus.COMPUTED
    assert triples(result.value.added_o2o) == {
        O2O("a", "b", "pix:observed_object_relation"),
        O2O("b", "a", "pix:observed_object_relation"),
    }
    assert [x.event_ids for x in result.value.added_o2o] == [("e2", "e3"), ("e2", "e3")]
    assert result.value.isolated_object_ids == ("c", "z")
    target = materialize_enriched_ocel(source, result)
    assert validate(target).valid
    assert result.value.target_digest == canonical_digest(target).identifier
    assert result.value.target_digest != result.source_digest
    assert set(target.e2o) == set(source.e2o)
    assert set(target.o2o) == set(source.o2o) | triples(result.value.added_o2o)
    for field in ("event_types", "object_types", "events", "objects", "import_info"):
        assert getattr(target, field) == getattr(source, field)
    assert len(source.o2o) == 2


def test_undirected_lexical_stores_one_orientation_and_changes_request_identity():
    source = example()
    both = enrich_object_relations(source)
    lexical = enrich_object_relations(
        source, ObjectRelationEnrichmentSpec(undirected="lexical")
    )
    assert triples(lexical.value.added_o2o) == {
        O2O("a", "b", "pix:observed_object_relation")
    }
    assert lexical.computation_id != both.computation_id


def test_directed_graph_does_not_add_reverse_edge():
    spec = ObjectRelationEnrichmentSpec(
        graph=ObjectGraphSpec("descendants"), qualifier="pix:observed_descendant"
    )
    result = enrich_object_relations(example(), spec)
    assert triples(result.value.added_o2o) == {O2O("a", "b", spec.qualifier)}
    assert result.value.added_o2o[0].event_ids == ("e2",)


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("cobirth", {("b", "c"): ("e2",), ("c", "b"): ("e2",)}),
        (
            "codeath",
            {
                ("a", "b"): ("e2",),
                ("b", "a"): ("e2",),
                ("c", "d"): ("e3",),
                ("d", "c"): ("e3",),
            },
        ),
        (
            "inheritance",
            {
                ("a", "b"): ("e2",),
                ("a", "c"): ("e2",),
                ("b", "c"): ("e2",),
                ("c", "d"): ("e3",),
            },
        ),
    ],
)
def test_birth_death_inheritance_hand_join_with_singleton_boundaries(kind, expected):
    source = OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("Thing"),),
        events=tuple(
            Event(f"e{i}", "A", T0 + timedelta(seconds=i)) for i in range(1, 4)
        ),
        objects=tuple(Object(name, "Thing") for name in "abcdz"),
        e2o=tuple(
            E2O(event, obj, "flow")
            for event, objects in (("e1", "a"), ("e2", "abc"), ("e3", "cd"))
            for obj in objects
        ),
    )
    result = enrich_object_relations(
        source,
        ObjectRelationEnrichmentSpec(
            graph=ObjectGraphSpec(kind), qualifier=f"pix:observed_{kind}"
        ),
    )
    assert {
        (row.relation.source, row.relation.target): row.event_ids
        for row in result.value.added_o2o
    } == expected
    target = materialize_enriched_ocel(source, result)
    assert set(target.o2o) == {O2O(a, b, f"pix:observed_{kind}") for a, b in expected}
    assert validate(target).valid


@pytest.mark.parametrize("qualifiers", [(), ("absent",), ("audit",)])
def test_graph_selection_with_no_edges_retains_isolates_and_digest(qualifiers):
    source = example()
    result = enrich_object_relations(
        source,
        ObjectRelationEnrichmentSpec(graph=ObjectGraphSpec(qualifiers=qualifiers)),
    )
    assert result.value.added_o2o == ()
    assert result.value.isolated_object_ids == ("a", "b", "c", "z")
    assert result.value.target_digest == result.source_digest
    assert materialize_enriched_ocel(source, result) == ComputationContext(source).log


def test_collision_rejects_whole_plan_or_skips_only_identical_orientation():
    source = example()
    existing = O2O("a", "b", "derived")
    source = replace(source, o2o=source.o2o + (existing,))
    rejected = enrich_object_relations(
        source, ObjectRelationEnrichmentSpec(qualifier="derived")
    )
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.issues[0].code == "existing_relation_collision"
    result = enrich_object_relations(
        source,
        ObjectRelationEnrichmentSpec(qualifier="derived", collision="skip_identical"),
    )
    assert triples(result.value.existing_o2o) == {existing}
    assert triples(result.value.added_o2o) == {O2O("b", "a", "derived")}
    target = materialize_enriched_ocel(source, result)
    assert target.o2o.count(existing) == 1


@pytest.mark.parametrize("collision", ["reject", "skip_identical"])
def test_output_qualifier_cannot_relabel_unrelated_original_relations(collision):
    source = example()
    source = replace(source, o2o=source.o2o + (O2O("z", "a", "derived"),))
    result = enrich_object_relations(
        source, ObjectRelationEnrichmentSpec(qualifier="derived", collision=collision)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "output_qualifier_conflict"


def test_lifecycle_manual_boundaries_singleton_both_and_selected_source_qualifiers():
    source = example()
    result = mark_lifecycle_qualifiers(source)
    first, last = "pix:first_observed", "pix:last_observed"
    assert triples(result.value.added_e2o) == {
        E2O("e1", "a", first),
        E2O("e3", "a", last),
        E2O("e2", "b", first),
        E2O("e3", "b", last),
        E2O("e4", "c", first),
        E2O("e4", "c", last),
    }
    assert result.value.isolated_object_ids == ("z",)
    target = materialize_enriched_ocel(source, result)
    assert set(source.e2o) <= set(target.e2o)
    assert set(target.e2o) - set(source.e2o) == triples(result.value.added_e2o)
    assert target.o2o == source.o2o
    assert target.objects == source.objects
    assert target.import_info == source.import_info
    selected = mark_lifecycle_qualifiers(
        source, LifecycleQualifierSpec(qualifiers=("audit",))
    )
    assert triples(selected.value.added_e2o) == {
        E2O("e2", "a", first),
        E2O("e2", "a", last),
        E2O("e4", "c", first),
        E2O("e4", "c", last),
    }
    assert all(x.source_qualifiers == ("audit",) for x in selected.value.added_e2o)
    assert selected.value.isolated_object_ids == ("b", "z")


def test_multiple_source_roles_are_witnessed_once_without_duplicate_additions():
    result = mark_lifecycle_qualifiers(
        example(), LifecycleQualifierSpec(qualifiers=("flow", "audit", "audit"))
    )
    a = [x for x in result.value.added_e2o if x.relation.object == "a"]
    assert len(a) == 2
    audit = mark_lifecycle_qualifiers(
        example(), LifecycleQualifierSpec(qualifiers=("audit",))
    )
    assert len([x for x in audit.value.added_e2o if x.relation.object == "a"]) == 2


def test_blank_source_qualifier_is_valid_incidence_and_custom_roles_are_preserved():
    source = example()
    source = replace(source, e2o=(E2O("e2", "a", ""), E2O("e2", "a", "audit")))
    result = mark_lifecycle_qualifiers(
        source,
        LifecycleQualifierSpec(
            qualifiers=("",), first_qualifier="start", last_qualifier="end"
        ),
    )
    assert triples(result.value.added_e2o) == {
        E2O("e2", "a", "start"),
        E2O("e2", "a", "end"),
    }
    assert all(x.source_qualifiers == ("",) for x in result.value.added_e2o)
    target = materialize_enriched_ocel(source, result)
    assert set(source.e2o) <= set(target.e2o)


def test_boundary_evidence_retains_all_selected_original_qualifiers():
    source = example()
    source = replace(source, e2o=source.e2o + (E2O("e1", "a", "audit"),))
    result = mark_lifecycle_qualifiers(source)
    first = next(
        x
        for x in result.value.added_e2o
        if x.relation.object == "a" and x.boundary == "first"
    )
    assert first.source_qualifiers == ("audit", "flow")
    assert first.boundary_event_ids == ("e1",)


def tied_source(*, interior=False, all_events=False):
    source = example()
    if interior:
        source = replace(source, e2o=source.e2o + (E2O("e4", "a", "flow"),))
        events = tuple(
            replace(e, time=T0 + timedelta(seconds=2)) if e.id == "e3" else e
            for e in source.events
        )
        # b's boundary ties would legitimately reject; isolate a for this example.
        source = replace(source, e2o=tuple(r for r in source.e2o if r.object == "a"))
    else:
        events = tuple(
            replace(e, time=T0) if all_events or e.id in ("e1", "e2") else e
            for e in source.events
        )
    return replace(source, events=events)


def test_endpoint_ties_reject_atomically_but_interior_ties_do_not():
    result = mark_lifecycle_qualifiers(tied_source())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "ambiguous_lifecycle_boundary"
    interior = mark_lifecycle_qualifiers(tied_source(interior=True))
    assert interior.status is ComputeStatus.COMPUTED
    assert {(x.relation.event, x.boundary) for x in interior.value.added_e2o} == {
        ("e1", "first"),
        ("e4", "last"),
    }


def test_all_tied_marks_every_boundary_event_with_both_roles():
    result = mark_lifecycle_qualifiers(
        tied_source(all_events=True), LifecycleQualifierSpec(tie_policy="all_tied")
    )
    a = [x for x in result.value.added_e2o if x.relation.object == "a"]
    assert len(a) == 6
    assert {(x.relation.event, x.boundary) for x in a} == {
        (e, role) for e in ("e1", "e2", "e3") for role in ("first", "last")
    }
    assert all(x.boundary_event_ids == ("e1", "e2", "e3") for x in a)


def test_event_id_tie_policy_chooses_extremes_and_records_all_tie_witnesses():
    result = mark_lifecycle_qualifiers(
        tied_source(all_events=True), LifecycleQualifierSpec(tie_policy="event_id")
    )
    a = [x for x in result.value.added_e2o if x.relation.object == "a"]
    assert {(x.relation.event, x.boundary) for x in a} == {
        ("e1", "first"),
        ("e3", "last"),
    }
    assert all(x.boundary_event_ids == ("e1", "e2", "e3") for x in a)
    assert all(x.code == "timestamp_tie_broken" for x in result.issues)
    assert len(result.issues) == 4  # first+last for a and b; c is a singleton.


def test_lifecycle_existing_roles_never_overwrite_and_can_skip_identical():
    source = example()
    initial = mark_lifecycle_qualifiers(source)
    target = materialize_enriched_ocel(source, initial)
    assert mark_lifecycle_qualifiers(target).status is ComputeStatus.UNAVAILABLE
    repeat = mark_lifecycle_qualifiers(
        target, LifecycleQualifierSpec(collision="skip_identical")
    )
    assert repeat.value.added_e2o == ()
    assert len(repeat.value.existing_e2o) == 6
    assert repeat.value.target_digest == repeat.source_digest
    assert materialize_enriched_ocel(target, repeat) == target
    wrong = replace(source, e2o=source.e2o + (E2O("e2", "a", "pix:first_observed"),))
    rejected = mark_lifecycle_qualifiers(
        wrong, LifecycleQualifierSpec(collision="skip_identical")
    )
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.issues[0].code == "output_qualifier_conflict"


@pytest.mark.parametrize(
    "operator,spec",
    [
        (
            enrich_object_relations,
            ObjectRelationEnrichmentSpec(isolated_objects="reject"),
        ),
        (mark_lifecycle_qualifiers, LifecycleQualifierSpec(isolated_objects="reject")),
    ],
)
def test_isolate_rejection_does_not_drop_source_objects(operator, spec):
    result = operator(example(), spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert all(x.code == "isolated_object" for x in result.issues)
    assert len(example().objects) == 4


def test_empty_selection_and_empty_log_are_computed_noop_without_invented_edges():
    source = example()
    result = mark_lifecycle_qualifiers(source, LifecycleQualifierSpec(qualifiers=()))
    assert result.value.added_e2o == ()
    assert result.value.isolated_object_ids == ("a", "b", "c", "z")
    assert result.value.target_digest == result.source_digest
    for operator in (enrich_object_relations, mark_lifecycle_qualifiers):
        empty = OCEL()
        result = operator(empty)
        assert result.status is ComputeStatus.COMPUTED
        assert materialize_enriched_ocel(empty, result) == empty


@pytest.mark.parametrize(
    "operator", [enrich_object_relations, mark_lifecycle_qualifiers]
)
def test_invalid_input_is_not_repaired_or_masked(operator):
    assert operator({}).status is ComputeStatus.INVALID_INPUT
    source = example()
    duplicate = replace(source, e2o=source.e2o + (source.e2o[0],))
    assert operator(duplicate).status is ComputeStatus.INVALID_INPUT
    dangling = replace(source, e2o=(E2O("missing", "a", ""),))
    assert operator(dangling).status is ComputeStatus.INVALID_INPUT
    with pytest.raises(TypeError):
        operator(source, "spec")


@pytest.mark.parametrize(
    "factory,kwargs,error",
    [
        (ObjectRelationEnrichmentSpec, {"graph": "interaction"}, TypeError),
        (ObjectRelationEnrichmentSpec, {"qualifier": " "}, ValueError),
        (ObjectRelationEnrichmentSpec, {"qualifier": 4}, TypeError),
        (ObjectRelationEnrichmentSpec, {"undirected": "random"}, ValueError),
        (ObjectRelationEnrichmentSpec, {"collision": "overwrite"}, ValueError),
        (ObjectRelationEnrichmentSpec, {"isolated_objects": "drop"}, ValueError),
        (LifecycleQualifierSpec, {"qualifiers": ["flow"]}, TypeError),
        (LifecycleQualifierSpec, {"qualifiers": (1,)}, TypeError),
        (
            LifecycleQualifierSpec,
            {"first_qualifier": "same", "last_qualifier": "same"},
            ValueError,
        ),
        (LifecycleQualifierSpec, {"last_qualifier": ""}, ValueError),
        (LifecycleQualifierSpec, {"tie_policy": "guess"}, ValueError),
        (LifecycleQualifierSpec, {"collision": None}, TypeError),
        (LifecycleQualifierSpec, {"isolated_objects": "drop"}, ValueError),
    ],
)
def test_bad_specs_rejected(factory, kwargs, error):
    with pytest.raises(error):
        factory(**kwargs)


def test_graph_inherited_order_ambiguity_and_explicit_tie_breaking():
    source = tied_source()
    rejected = enrich_object_relations(
        source, ObjectRelationEnrichmentSpec(graph=ObjectGraphSpec("descendants"))
    )
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.issues[0].code == "ambiguous_event_order"
    allowed = enrich_object_relations(
        source,
        ObjectRelationEnrichmentSpec(
            graph=ObjectGraphSpec("descendants", tie_policy="event_id")
        ),
    )
    assert allowed.status is ComputeStatus.COMPUTED
    assert allowed.issues[0].code == "timestamp_tie_broken"
    assert validate(materialize_enriched_ocel(source, allowed)).valid


@pytest.mark.parametrize(
    "operator", [enrich_object_relations, mark_lifecycle_qualifiers]
)
def test_exact_source_semantics_metadata_and_order_invariance(operator):
    source = example()
    result = operator(source)
    reordered = replace(
        source,
        events=tuple(reversed(source.events)),
        objects=tuple(reversed(source.objects)),
        e2o=tuple(reversed(source.e2o)),
        o2o=tuple(reversed(source.o2o)),
    )
    assert operator(reordered) == result
    assert materialize_enriched_ocel(
        ComputationContext(reordered), result
    ) == materialize_enriched_ocel(source, result)
    other = replace(source, o2o=())
    with pytest.raises(ValueError, match="source digest"):
        materialize_enriched_ocel(other, result)
    metadata = replace(
        source, import_info=replace(source.import_info, source="another provenance")
    )
    assert operator(metadata) == result
    assert (
        materialize_enriched_ocel(metadata, result).import_info == metadata.import_info
    )
    shifted = replace(
        source,
        events=tuple(
            replace(e, time=e.time.astimezone(timezone(timedelta(hours=9))))
            for e in source.events
        ),
    )
    assert operator(shifted) == result


@pytest.mark.parametrize(
    "operator", [enrich_object_relations, mark_lifecycle_qualifiers]
)
def test_materializer_recomputes_full_envelope_value_and_witnesses(operator):
    source = example()
    result = operator(source)
    changes = [
        replace(result, computation_id="tampered"),
        replace(result, operator_version="2.0.0"),
        replace(result, parent_computation_ids=("invented",)),
        replace(result, issues=(ComputeIssue("invented", "tamper"),)),
        replace(result, value=replace(result.value, target_digest="forged")),
        replace(result, value=replace(result.value, isolated_object_ids=())),
    ]
    if result.value.added_o2o:
        additions = result.value.added_o2o
        changes.append(
            replace(
                result,
                value=replace(
                    result.value, added_o2o=additions[1:], existing_o2o=additions[:1]
                ),
            )
        )
        changes.append(
            replace(
                result,
                value=replace(
                    result.value,
                    added_o2o=(replace(additions[0], event_ids=("e1",)),)
                    + additions[1:],
                ),
            )
        )
        changes.append(replace(result, spec=replace(result.spec, undirected="lexical")))
    else:
        additions = result.value.added_e2o
        changes.append(
            replace(
                result,
                value=replace(
                    result.value, added_e2o=additions[1:], existing_e2o=additions[:1]
                ),
            )
        )
        changes.append(
            replace(
                result,
                value=replace(
                    result.value,
                    added_e2o=(replace(additions[0], source_qualifiers=("invented",)),)
                    + additions[1:],
                ),
            )
        )
        changes.append(replace(result, spec=replace(result.spec, qualifiers=())))
    for changed in changes:
        with pytest.raises(ValueError, match="identity or relation evidence"):
            materialize_enriched_ocel(source, changed)


def test_materializer_rejects_wrong_operator_spec_status_and_bad_source():
    source = example()
    result = enrich_object_relations(source)
    with pytest.raises(TypeError):
        materialize_enriched_ocel(source, "result")
    with pytest.raises(ValueError, match="computed OCEL enrichment"):
        materialize_enriched_ocel(source, replace(result, operator_id="other"))
    with pytest.raises(ValueError, match="incompatible specification"):
        materialize_enriched_ocel(
            source, replace(result, spec=LifecycleQualifierSpec())
        )
    with pytest.raises(ValueError, match="computed OCEL enrichment"):
        materialize_enriched_ocel(
            source,
            enrich_object_relations(
                source, ObjectRelationEnrichmentSpec(isolated_objects="reject")
            ),
        )
    with pytest.raises(ValueError, match="invalid source"):
        materialize_enriched_ocel(
            replace(source, e2o=(E2O("unknown", "a", ""),)), result
        )
    with pytest.raises(FrozenInstanceError):
        result.value.target_digest = "changed"


@pytest.mark.parametrize(
    "operator", [enrich_object_relations, mark_lifecycle_qualifiers]
)
def test_result_json_roundtrip_and_materialization(operator):
    from pix import results

    source = example()
    result = operator(source)
    restored = results.result_from_json(results.result_json_bytes(result))
    assert restored == result
    assert materialize_enriched_ocel(source, restored) == materialize_enriched_ocel(
        source, result
    )
