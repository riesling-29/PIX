from dataclasses import replace
from xml.etree import ElementTree as ET

import pytest

from pix.compute.model_semantics import fire, is_enabled, is_final
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.model_io.common import ModelIOError, XMLLimits
from pix.model_io.pnml import dumps_pnml, loads_pnml


def weighted_net():
    return PetriNet(
        (Place("input"), Place("middle"), Place("output")),
        (Transition("silent"), Transition("visible", "활동 <&>")),
        (
            Arc("input", "silent", 2),
            Arc("silent", "middle", 3),
            Arc("middle", "visible", 3),
            Arc("visible", "output", 4),
        ),
        Marking((("input", 2),)),
        Marking((("output", 4),)),
    )


def test_weighted_silent_markings_roundtrip():
    model = weighted_net()
    payload = dumps_pnml(model)
    imported = loads_pnml(payload)
    assert imported.model == model
    assert imported.format == "pnml"
    assert imported.format_version == "2009"
    assert imported.profile_version == "1.0.0"
    assert len(imported.source_sha256) == 64
    again = loads_pnml(dumps_pnml(imported))
    assert again.model == model
    assert dict(again.source_ids) == dict(imported.source_ids)
    assert b"$invisible$" in payload


def flat_document(
    content,
    final='<finalmarkings><marking><place idref="p1"><text>1</text></place></marking></finalmarkings>',
):
    return (
        '<pnml><net id="n" type="http://www.pnml.org/version-2009/grammar/pnmlcoremodel">'
        + content
        + final
        + "</net></pnml>"
    )


SIMPLE = (
    '<place id="p0"><initialMarking><text>1</text></initialMarking></place>'
    '<place id="p1"/><transition id="t"><name><text>A</text></name></transition>'
    '<arc id="a" source="p0" target="t"/><arc id="b" source="t" target="p1"/>'
)


def test_common_pm4py_flat_dialect_and_duplicate_activity_labels():
    source = flat_document(
        SIMPLE.replace(
            '<arc id="a"',
            '<transition id="u"><name><text>A</text></name></transition><arc id="a"',
        )
    )
    imported = loads_pnml(source)
    assert [t.id for t in imported.model.transitions] == ["t", "u"]
    assert [t.activity for t in imported.model.transitions] == ["A", "A"]
    assert loads_pnml(dumps_pnml(imported)).model == imported.model
    assert dict(loads_pnml(dumps_pnml(imported)).source_ids) == dict(
        imported.source_ids
    )


@pytest.mark.parametrize(
    "insert",
    [
        "<arctype><text>inhibitor</text></arctype>",
        '<type value="reset"/>',
        '<toolspecific tool="StochasticPetriNet" version="0.2"/>',
    ],
)
def test_reject_unsupported_arc_semantics(insert):
    source = flat_document(
        SIMPLE.replace(
            '<arc id="a" source="p0" target="t"/>',
            '<arc id="a" source="p0" target="t">' + insert + "</arc>",
        )
    )
    with pytest.raises(ModelIOError) as failure:
        loads_pnml(source)
    assert failure.value.code == "unsupported_feature"
    assert failure.value.element


@pytest.mark.parametrize(
    ("before", "after", "code"),
    [
        ('id="b"', 'id="a"', "duplicate_id"),
        ('target="p1"', 'target="absent"', "invalid_model"),
        ('source="p0"', 'source="p1" targetXX="p1"', "unsupported_feature"),
        ('<place id="p1"/>', '<place id="p0"/>', "duplicate_id"),
        (
            '<transition id="t">',
            '<transition id="t" guard="x &gt; 1">',
            "unsupported_feature",
        ),
        (
            '<place id="p1"/>',
            '<place id="p1"><capacity><text>1</text></capacity></place>',
            "unsupported_feature",
        ),
    ],
)
def test_reject_invalid_source(before, after, code):
    with pytest.raises(ModelIOError) as failure:
        loads_pnml(flat_document(SIMPLE.replace(before, after)))
    assert failure.value.code == code


def test_never_guess_final_marking_from_sinks():
    with pytest.raises(ModelIOError, match="finalmarkings"):
        loads_pnml(flat_document(SIMPLE, final=""))


def test_multiple_final_markings_and_duplicate_place_ref_rejected():
    for final in (
        "<finalmarkings><marking/><marking/></finalmarkings>",
        '<finalmarkings><marking><place idref="p1"><text>1</text></place><place idref="p1"><text>0</text></place></marking></finalmarkings>',
    ):
        with pytest.raises(ModelIOError):
            loads_pnml(flat_document(SIMPLE, final=final))


@pytest.mark.parametrize("value", ["-1", "1.5", "true", "0", "1e10"])
def test_arc_weights_require_positive_integers(value):
    source = SIMPLE.replace(
        '<arc id="a" source="p0" target="t"/>',
        '<arc id="a" source="p0" target="t"><inscription><text>'
        + value
        + "</text></inscription></arc>",
    )
    with pytest.raises(ModelIOError):
        loads_pnml(flat_document(source))


def test_zero_marking_is_empty_and_not_inferred():
    imported = loads_pnml(
        flat_document(
            SIMPLE.replace("<text>1</text>", "<text>0</text>"),
            final="<finalmarkings><marking/></finalmarkings>",
        )
    )
    assert imported.model.initial_marking == Marking()
    assert imported.model.final_marking == Marking()


def test_graphics_omission_is_reported_names_preserved():
    source = flat_document(
        SIMPLE.replace(
            '<place id="p1"/>',
            '<place id="p1"><name><text>finished</text></name><graphics><position x="1" y="2"/></graphics></place>',
        )
    )
    imported = loads_pnml(source)
    assert imported.presentation_ignored == ("place[p1]/graphics",)
    output = dumps_pnml(imported)
    assert b"finished" in output
    assert b"graphics" not in output


def test_unknown_graphics_extension_is_not_hidden():
    source = flat_document(
        SIMPLE.replace(
            '<place id="p1"/>',
            '<place id="p1"><graphics><guard>predicate</guard></graphics></place>',
        )
    )
    with pytest.raises(ModelIOError, match="guard"):
        loads_pnml(source)


def test_foreign_namespace_is_not_interpreted_by_local_name():
    source = flat_document(
        SIMPLE.replace('<place id="p1"/>', '<x:place xmlns:x="urn:evil" id="p1"/>')
    )
    with pytest.raises(ModelIOError, match="namespace"):
        loads_pnml(source)


@pytest.mark.parametrize(
    "payload",
    [
        b'<!DOCTYPE pnml [<!ENTITY stolen SYSTEM "file:///C:/secret.txt">]><pnml>&stolen;</pnml>',
        b'<!DOCTYPE pnml SYSTEM "https://example.invalid/remote.dtd"><pnml/>',
        b'<!DOCTYPE pnml [<!ENTITY a "aaaaaaaa">]><pnml>&a;</pnml>',
    ],
)
def test_entities_and_dtd_are_rejected_before_expansion(payload):
    with pytest.raises(ModelIOError) as failure:
        loads_pnml(payload)
    assert failure.value.code == "unsafe_xml"


@pytest.mark.parametrize(
    "limit",
    [XMLLimits(max_bytes=30), XMLLimits(max_elements=3), XMLLimits(max_depth=2)],
)
def test_parse_budgets_fail_closed(limit):
    with pytest.raises(ModelIOError) as failure:
        loads_pnml(dumps_pnml(weighted_net()), limits=limit)
    assert failure.value.code == "resource_limit"


def test_utf16_and_malformed_xml_and_pi_rejected():
    with pytest.raises(ModelIOError, match="UTF-8"):
        loads_pnml(flat_document(SIMPLE).encode("utf-16"))
    with pytest.raises(ModelIOError) as failure:
        loads_pnml("<pnml>")
    assert failure.value.code == "invalid_xml"
    with pytest.raises(ModelIOError, match="processing"):
        loads_pnml("<?do something?>" + flat_document(SIMPLE))


def test_invalid_xml_export_never_returns_payload():
    model = weighted_net()
    model = replace(
        model, transitions=(Transition("silent"), Transition("visible", "bad\x01label"))
    )
    with pytest.raises(ModelIOError) as error:
        dumps_pnml(model)
    assert error.value.format == "pnml"


def test_id_generation_avoids_collisions():
    model = PetriNet(
        (Place("pix_net"), Place("pix_page")),
        (Transition("pix_arc_0", "A"),),
        (Arc("pix_net", "pix_arc_0"), Arc("pix_arc_0", "pix_page")),
        Marking((("pix_net", 1),)),
        Marking((("pix_page", 1),)),
    )
    payload = dumps_pnml(model)
    tree = ET.fromstring(payload)
    ids = [item.get("id") for item in tree.iter() if item.get("id") is not None]
    assert len(ids) == len(set(ids))
    assert loads_pnml(payload).model == model


def test_nonblank_transition_without_name_uses_explicit_id():
    imported = loads_pnml(
        flat_document(SIMPLE.replace("<name><text>A</text></name>", ""))
    )
    assert imported.model.transitions[0] == Transition("t", "t")


def test_ambiguous_silence_conventions_rejected():
    source = flat_document(
        SIMPLE.replace(
            "<name><text>A</text></name>",
            '<toolspecific tool="SomeTool" version="1" activity="$invisible$"/>',
        )
    )
    with pytest.raises(ModelIOError, match="ProM"):
        loads_pnml(source)


def test_retained_ids_cannot_collide_on_export():
    imported = loads_pnml(dumps_pnml(weighted_net()))
    bad = replace(imported, source_ids=(("net", "input"),))
    with pytest.raises(ModelIOError, match="retained"):
        dumps_pnml(bad)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format_version", "newer"),
        ("profile_version", "9.0.0"),
        ("profile", "unknown"),
        ("source_ids", (("nonexistent", "n"),)),
        ("metadata", (("net_name", "one"), ("net_name", "two"))),
        ("metadata", (("guard", "x>1"),)),
        ("metadata", (("page_mode", "many"),)),
    ],
)
def test_forged_profile_or_metadata_is_not_silently_dropped(field, value):
    imported = replace(loads_pnml(dumps_pnml(weighted_net())), **{field: value})
    with pytest.raises(ModelIOError):
        dumps_pnml(imported)


def test_blank_visible_label_is_structured_model_error():
    with pytest.raises(ModelIOError) as error:
        loads_pnml(flat_document(SIMPLE.replace("<text>A</text>", "<text> </text>")))
    assert error.value.code == "invalid_model"
    assert error.value.element == "transition"


def test_utf16_without_bom_cannot_bypass_utf8_profile():
    with pytest.raises(ModelIOError) as error:
        loads_pnml(flat_document(SIMPLE).encode("utf-16-le"))
    assert error.value.code == "unsupported_encoding"


def test_text_cannot_hide_unsupported_arc_semantics():
    source = SIMPLE.replace(
        '<arc id="a" source="p0" target="t"/>',
        '<arc id="a" source="p0" target="t">inhibitor</arc>',
    )
    with pytest.raises(ModelIOError):
        loads_pnml(flat_document(source))


@pytest.mark.parametrize("label", ["A\rB", "A\r\nB", "A\tB\nC", "A\u0085B"])
def test_xml_text_normalization_does_not_change_activity_labels(label):
    model = replace(
        weighted_net(), transitions=(Transition("silent"), Transition("visible", label))
    )
    assert loads_pnml(dumps_pnml(model)).model == model


def test_imported_text_character_reference_remains_exact():
    imported = loads_pnml(
        flat_document(SIMPLE.replace("<text>A</text>", "<text>A&#13;B</text>"))
    )
    assert imported.model.transitions[0].activity == "A\rB"
    assert loads_pnml(dumps_pnml(imported)).model == imported.model


def test_imported_weighted_net_firing_consumes_and_produces_exact_multiplicity():
    net = loads_pnml(dumps_pnml(weighted_net())).model
    assert not is_enabled(net, Marking((("input", 1),)), "silent")
    assert not is_enabled(net, net.initial_marking, "visible")
    middle = fire(net, net.initial_marking, "silent")
    assert middle == Marking((("middle", 3),))
    assert is_enabled(net, middle, "visible")
    final = fire(net, middle, "visible")
    assert final == Marking((("output", 4),))
    assert is_final(net, final)
