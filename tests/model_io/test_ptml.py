"""PTML semantics, source identity, and fail-closed exchange boundaries."""

from collections import Counter, deque
from dataclasses import replace
from hashlib import sha256
from xml.etree import ElementTree as ET

import pytest

from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.discovery import ProcessTree
from pix.model_io.common import ModelIOError, XMLLimits
from pix.model_io.ptml import dumps_ptml, loads_ptml


def leaf(label):
    return ProcessTree("activity", label)


def document(nodes, edges="", root="root", attributes='id="tree-17" name="Example"'):
    return f'<ptml><processTree root="{root}" {attributes}>{nodes}{edges}</processTree></ptml>'


def edge(source, target, name=None):
    return f'<parentsNode id="{name or source + "-" + target}" sourceId="{source}" targetId="{target}" />'


def accepts(tree, word):
    """Independent weighted-net reachability oracle; no imported tree rewriting."""
    net = process_tree_to_petri_net(tree)
    pending = deque([(net.initial_marking.tokens, 0)])
    seen = set(pending)
    while pending:
        marking, offset = pending.popleft()
        if marking == net.final_marking.tokens and offset == len(word):
            return True
        for transition in net.transitions:
            if transition.activity is not None:
                if offset == len(word) or transition.activity != word[offset]:
                    continue
                next_offset = offset + 1
            else:
                next_offset = offset
            tokens = Counter(dict(marking))
            inputs = [a for a in net.arcs if a.target == transition.id]
            if any(tokens[a.source] < a.weight for a in inputs):
                continue
            for arc in inputs:
                tokens[arc.source] -= arc.weight
            for arc in net.arcs:
                if arc.source == transition.id:
                    tokens[arc.target] += arc.weight
            state = tuple(sorted((p, n) for p, n in tokens.items() if n)), next_offset
            if state not in seen:
                assert len(seen) < 10_000
                seen.add(state)
                pending.append(state)
    return False


@pytest.mark.parametrize(
    "model",
    [
        leaf("A"),
        leaf('검토 & 승인 <"x">'),
        ProcessTree("tau"),
        ProcessTree("sequence", children=(leaf("B"), leaf("A"))),
        ProcessTree("xor", children=(leaf("B"), ProcessTree("tau"))),
        ProcessTree("parallel", children=(leaf("B"), leaf("A"), leaf("C"))),
        ProcessTree("loop", children=(leaf("A"), leaf("B"))),
        ProcessTree(
            "sequence",
            children=(
                ProcessTree(
                    "loop",
                    children=(
                        ProcessTree("xor", children=(leaf("A"), leaf("B"))),
                        ProcessTree("parallel", children=(leaf("C"), leaf("D"))),
                    ),
                ),
                ProcessTree("tau"),
            ),
        ),
    ],
)
def test_roundtrip_all_operators_and_order(model):
    payload = dumps_ptml(model)
    result = loads_ptml(payload)
    assert result.model == model
    assert result.format == "ptml"
    assert result.profile == "ptml.binary-loop-plus-tau-exit.v1"
    assert result.profile_version == "1.0.0"
    assert result.format_version == "unversioned"
    assert result.source_sha256 == sha256(payload).hexdigest()
    assert dumps_ptml(model) == payload
    assert dumps_ptml(result) == payload


def test_parent_edge_document_order_defines_sequence_not_node_or_id_order():
    source = document(
        '<manualTask id="a" name="A"/><sequence id="root" name=""/>'
        '<manualTask id="z" name="Z"/>',
        edge("root", "z") + edge("root", "a"),
    )
    model = loads_ptml(source).model
    assert tuple(child.activity for child in model.children) == ("Z", "A")
    assert accepts(model, "ZA")
    assert not accepts(model, "AZ")


def test_forward_references_are_valid_and_order_survives_interleaving():
    source = document(
        edge("root", "b")
        + '<manualTask id="b" name="B"/>'
        + edge("root", "a")
        + '<sequence id="root"/>'
        '<manualTask id="a" name="A"/>'
    )
    assert loads_ptml(source).model == ProcessTree(
        "sequence", children=(leaf("B"), leaf("A"))
    )


def test_equal_labels_and_reused_native_instances_retain_occurrence_ids():
    same_instance = leaf("Inspect")
    model = ProcessTree("sequence", children=(same_instance, same_instance))
    imported = loads_ptml(dumps_ptml(model))
    ids = dict(imported.source_ids)
    assert ids["node:/0/0"] != ids["node:/0/1"]
    assert imported.model == model


def test_prom_loop_tau_exit_reduction_preserves_language_and_source_ids():
    source = document(
        '<xorLoop id="root" name="retry"/><manualTask id="do" name="A"/>'
        '<manualTask id="redo" name="B"/><automaticTask id="exit" name="done"/>',
        edge("root", "do", "edge-1")
        + edge("root", "redo", "edge-2")
        + edge("root", "exit", "edge-3"),
    )
    imported = loads_ptml(source)
    assert imported.model == ProcessTree("loop", children=(leaf("A"), leaf("B")))
    assert dict(imported.metadata)["normalized_tau_exit:/0"] == "exit"
    assert dict(imported.source_ids)["loop_exit:/0"] == "exit"
    for accepted in ("A", "ABA", "ABABA"):
        assert accepts(imported.model, accepted)
    for rejected in ("", "B", "AB", "AA", "BA"):
        assert not accepts(imported.model, rejected)
    exported = loads_ptml(dumps_ptml(imported))
    assert exported.model == imported.model
    assert dict(exported.source_ids) == dict(imported.source_ids)
    assert dict(exported.metadata) == dict(imported.metadata)


def test_binary_loop_adds_explicit_tau_exit_only_on_export():
    imported = loads_ptml(
        document(
            '<xorLoop id="root"/><manualTask id="a" name="A"/><manualTask id="b" name="B"/>',
            edge("root", "a") + edge("root", "b"),
        )
    )
    assert not any(key.startswith("loop_exit:") for key, _ in imported.source_ids)
    exported = loads_ptml(dumps_ptml(imported))
    assert exported.model == imported.model
    assert "loop_exit:/0" in dict(exported.source_ids)


def test_nested_loops_emit_do_redo_exit_order_for_each_parent():
    nested = ProcessTree("loop", children=(leaf("C"), leaf("D")))
    model = ProcessTree("loop", children=(leaf("A"), nested))
    result = loads_ptml(dumps_ptml(model))
    assert result.model == model
    assert (
        len(
            [
                key
                for key, _ in result.metadata
                if key.startswith("normalized_tau_exit:")
            ]
        )
        == 2
    )


@pytest.mark.parametrize("operator", ["sequence", "xor", "parallel"])
def test_noncommutative_representation_order_is_not_sorted(operator):
    model = ProcessTree(operator, children=(leaf("Z"), leaf("A")))
    assert loads_ptml(dumps_ptml(model)).model.children == model.children


@pytest.mark.parametrize("tag", ["or", "interleaved", "inclusive", "event", "unknown"])
def test_unsupported_operators_are_not_silently_dropped(tag):
    with pytest.raises(ModelIOError, match="unsupported source element"):
        loads_ptml(document(f'<{tag} id="root" name=""/>'))


@pytest.mark.parametrize(
    "source,code",
    [
        ("<processTree/>", "invalid_structure"),
        ("<ptml/>", "invalid_structure"),
        ("<ptml><processTree/><processTree/></ptml>", "invalid_structure"),
        (document('<manualTask id="root"/>'), "invalid_structure"),
        (document('<manualTask id="root" name="   "/>'), "invalid_structure"),
        (document('<automaticTask id=" "/>'), "invalid_structure"),
        (
            document('<automaticTask id="root"/><automaticTask id="root"/>'),
            "duplicate_id",
        ),
        (document('<automaticTask id="tree-17"/>'), "duplicate_id"),
        (document('<automaticTask id="x"/>'), "dangling_reference"),
        (
            document('<automaticTask id="root"/>', edge("root", "missing")),
            "dangling_reference",
        ),
        (
            document('<automaticTask id="root"/>', edge("root", "root")),
            "invalid_structure",
        ),
        (
            document('<automaticTask id="root"/><automaticTask id="x"/>'),
            "invalid_structure",
        ),
        (
            document('<sequence id="root"/><automaticTask id="x"/>', edge("root", "x")),
            "invalid_structure",
        ),
        (
            document(
                '<automaticTask id="root"/><automaticTask id="x"/>', edge("root", "x")
            ),
            "invalid_structure",
        ),
        (
            document(
                '<sequence id="root"/><automaticTask id="x"/>',
                edge("root", "x", "one") + edge("root", "x", "two"),
            ),
            "invalid_structure",
        ),
        (
            document(
                '<sequence id="root"/><automaticTask id="x"/><automaticTask id="y"/>',
                edge("root", "x", "one") + edge("root", "y", "one"),
            ),
            "duplicate_id",
        ),
        (
            document(
                '<automaticTask id="root"/><sequence id="x"/><sequence id="y"/>',
                edge("x", "y") + edge("y", "x"),
            ),
            "invalid_structure",
        ),
        (document('<automaticTask id="root" bogus="ignored"/>'), "unsupported_feature"),
        (
            document('<automaticTask id="root"><graphics/></automaticTask>'),
            "unsupported_feature",
        ),
        (
            document('<automaticTask id="root">ignored</automaticTask>'),
            "unsupported_feature",
        ),
        (
            document('<automaticTask id="root"/>').replace(
                "<ptml>", '<ptml xmlns="urn:foreign">'
            ),
            "unsupported_feature",
        ),
        (
            document('<f:automaticTask xmlns:f="urn:foreign" id="root"/>'),
            "unsupported_feature",
        ),
    ],
)
def test_invalid_structure_and_unsupported_semantics_fail_closed(source, code):
    with pytest.raises(ModelIOError) as error:
        loads_ptml(source)
    assert error.value.format == "ptml"
    assert error.value.code == code


@pytest.mark.parametrize(
    "exit_node",
    [
        '<manualTask id="exit" name="C"/>',
        '<sequence id="exit"/><automaticTask id="extra1"/><automaticTask id="extra2"/>',
    ],
)
def test_non_tau_loop_exit_is_rejected_without_lossy_conversion(exit_node):
    edges = edge("root", "a") + edge("root", "b") + edge("root", "exit")
    if "sequence" in exit_node:
        edges += edge("exit", "extra1") + edge("exit", "extra2")
    with pytest.raises(ModelIOError, match="silent third"):
        loads_ptml(
            document(
                '<xorLoop id="root"/><manualTask id="a" name="A"/><manualTask id="b" name="B"/>'
                + exit_node,
                edges,
            )
        )


@pytest.mark.parametrize("count", [0, 1, 4])
def test_unsupported_loop_arities(count):
    nodes = '<xorLoop id="root"/>' + "".join(
        f'<automaticTask id="c{i}"/>' for i in range(count)
    )
    edges = "".join(edge("root", f"c{i}") for i in range(count))
    with pytest.raises(ModelIOError, match="Loops require"):
        loads_ptml(document(nodes, edges))


@pytest.mark.parametrize(
    "prefix",
    [
        '<!DOCTYPE ptml [<!ENTITY x "boom">]>',
        '<!DOCTYPE ptml SYSTEM "file:///should-not-be-read">',
        "<?execute harmful?>",
    ],
)
def test_unsafe_xml_is_rejected(prefix):
    with pytest.raises(ModelIOError):
        loads_ptml(prefix + document('<automaticTask id="root"/>'))


@pytest.mark.parametrize(
    "limits",
    [XMLLimits(max_bytes=12), XMLLimits(max_elements=2), XMLLimits(max_depth=2)],
)
def test_xml_resource_limits(limits):
    with pytest.raises(ModelIOError) as error:
        loads_ptml(document('<automaticTask id="root"/>'), limits=limits)
    assert error.value.code == "resource_limit"


def test_logical_depth_bound_applies_to_flat_xml():
    model = leaf("A")
    for _ in range(5):
        model = ProcessTree("sequence", children=(model, leaf("B")))
    payload = dumps_ptml(model)
    assert loads_ptml(payload).model == model
    with pytest.raises(ModelIOError, match="Logical process-tree depth"):
        loads_ptml(payload, limits=XMLLimits(max_depth=4))


def test_wrapper_preserves_display_metadata_and_unknown_ids_without_semantic_alias():
    parsed = loads_ptml(
        document(
            '<automaticTask id="foreign-ID" name="Skip &amp; finish"/>',
            root="foreign-ID",
        )
    )
    restored = loads_ptml(dumps_ptml(parsed))
    assert restored.source_ids == parsed.source_ids
    assert restored.metadata == parsed.metadata
    assert restored.model == ProcessTree("tau")


def test_generated_exit_id_cannot_collide_with_imported_id():
    parsed = loads_ptml(
        document(
            '<xorLoop id="root"/><manualTask id="pix_loop_exit__0" name="A"/><automaticTask id="b"/>',
            edge("root", "pix_loop_exit__0") + edge("root", "b"),
        )
    )
    result = loads_ptml(dumps_ptml(parsed))
    ids = [value for _, value in result.source_ids]
    assert len(ids) == len(set(ids))


def test_export_rejects_incompatible_or_stale_wrapper_metadata():
    parsed = loads_ptml(dumps_ptml(leaf("A")))
    with pytest.raises(ModelIOError, match="another format"):
        dumps_ptml(replace(parsed, format="pnml"))
    with pytest.raises(ModelIOError, match="unique"):
        dumps_ptml(
            replace(
                parsed,
                source_ids=(*parsed.source_ids, ("extra", parsed.source_ids[0][1])),
            )
        )
    with pytest.raises(ModelIOError, match="do not match"):
        dumps_ptml(
            replace(parsed, source_ids=(*parsed.source_ids, ("node:/0/3", "extra")))
        )
    with pytest.raises(TypeError):
        dumps_ptml("A")


def test_export_rejects_forbidden_xml_characters():
    with pytest.raises(ModelIOError):
        dumps_ptml(leaf("A\x01B"))


def test_export_counts_source_tree_id_node_and_edge_ids_separately():
    model = ProcessTree("sequence", children=(leaf("A"), leaf("B")))
    root = ET.fromstring(dumps_ptml(model))
    ids = [element.attrib["id"] for element in root.iter() if "id" in element.attrib]
    assert len(ids) == 6
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "ptml.any-semantics"),
        ("format_version", "future"),
        ("profile_version", "2.0.0"),
    ],
)
def test_export_rejects_unimplemented_wrapper_profile_versions(field, value):
    parsed = loads_ptml(dumps_ptml(leaf("A")))
    with pytest.raises(ModelIOError, match="profile or version") as error:
        dumps_ptml(replace(parsed, **{field: value}))
    assert error.value.code == "invalid_model"
    assert error.value.format == "ptml"


@pytest.mark.parametrize(
    "operator,field,value",
    [
        ("activity", "children", (leaf("B"),)),
        ("activity", "activity", None),
        ("activity", "activity", "   "),
        ("activity", "activity", 17),
        ("activity", "operator", "unsupported"),
        ("tau", "activity", "dropped label"),
        ("tau", "children", (leaf("B"),)),
        ("sequence", "children", (leaf("B"),)),
        ("sequence", "children", [leaf("A"), leaf("B")]),
        ("sequence", "children", (leaf("A"), "not-a-node")),
        ("sequence", "activity", "dropped label"),
        ("loop", "children", (leaf("A"),)),
        ("loop", "children", (leaf("A"), leaf("B"), ProcessTree("tau"))),
    ],
)
def test_export_revalidates_forged_process_tree_nodes(operator, field, value):
    model = (
        leaf("A")
        if operator == "activity"
        else ProcessTree("tau")
        if operator == "tau"
        else ProcessTree(operator, children=(leaf("A"), leaf("B")))
    )
    object.__setattr__(model, field, value)
    with pytest.raises(ModelIOError, match="Invalid ProcessTree node") as error:
        dumps_ptml(model)
    assert error.value.code == "invalid_model"
    assert error.value.format == "ptml"


def test_export_revalidates_nested_nodes_and_bounds_forged_cycles():
    bad = leaf("A")
    parent = ProcessTree("sequence", children=(bad, leaf("B")))
    object.__setattr__(bad, "activity", None)
    with pytest.raises(ModelIOError, match="Invalid ProcessTree node"):
        dumps_ptml(parent)
    cycle = ProcessTree("sequence", children=(leaf("A"), leaf("B")))
    object.__setattr__(cycle, "children", (cycle, leaf("B")))
    with pytest.raises(ModelIOError, match="export limits"):
        dumps_ptml(cycle)


@pytest.mark.parametrize(
    "metadata",
    [
        (("tree_name", "one"), ("tree_name", "two")),
        (("unknown-display-field", "value"),),
        (("name:node:/0", "must not overwrite an activity"),),
        (("name:node:/0/9", "stale child name"),),
        (("normalized_tau_exit:/0", "not a loop"),),
        (("tree_name", 12),),
        (("tree_name", "value", "unexpected third field"),),
        [("tree_name", "mutable metadata")],
    ],
)
def test_export_refuses_ambiguous_or_unsupported_metadata(metadata):
    parsed = loads_ptml(dumps_ptml(leaf("A")))
    with pytest.raises(ModelIOError) as error:
        dumps_ptml(replace(parsed, metadata=metadata))
    assert error.value.code == "invalid_model"


def test_export_rejects_tau_normalization_evidence_with_wrong_identity():
    parsed = loads_ptml(
        dumps_ptml(ProcessTree("loop", children=(leaf("A"), leaf("B"))))
    )
    metadata = tuple(
        (key, "wrong ID" if key.startswith("normalized_tau_exit:") else value)
        for key, value in parsed.metadata
    )
    with pytest.raises(ModelIOError, match="does not match"):
        dumps_ptml(replace(parsed, metadata=metadata))


@pytest.mark.parametrize(
    "ids",
    [
        (("node:/0", "duplicate"), ("node:/0", "different")),
        (("node:/0", ""),),
        (("node:/0", 123),),
        (("node:/0", "value", "extra"),),
    ],
)
def test_export_validates_identifier_metadata_before_serialization(ids):
    parsed = loads_ptml(dumps_ptml(leaf("A")))
    with pytest.raises(ModelIOError) as error:
        dumps_ptml(replace(parsed, source_ids=ids))
    assert error.value.code == "invalid_model"
