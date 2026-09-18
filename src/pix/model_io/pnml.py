"""PNML 2009 weighted P/T exchange with explicit accepting-net extensions.

This profile accepts one flat net or one page, integer-weight ordinary arcs,
the ProM ``activity='$invisible$'`` convention and exactly one explicit final
marking. No sink-based final marking or silent-label heuristic is used. Reset,
inhibitor, stochastic, colored and data-net extensions are refused. Graphics
are named in the import evidence and omitted; semantic IDs and labels remain.

PNML vocabulary: https://www.pnml.org/version-2009/grammar/pnml
Interchange conventions checked against the pinned PM4Py 2.7.23.8 serializer;
this implementation does not import or execute that library.
"""

from __future__ import annotations

import json
from xml.etree.ElementTree import Element, SubElement

from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition

from .common import (
    ParsedModel,
    XMLLimits,
    fail,
    integer,
    local,
    parse_xml,
    source_digest,
    strict,
    xml_bytes,
)

FORMAT = "pnml"
PROFILE = "pix.pnml2009.pt-prom-accepting"
NAMESPACE = "http://www.pnml.org/version-2009/grammar/pnml"
PT_TYPE = "http://www.pnml.org/version-2009/grammar/ptnet"
CORE_TYPE = "http://www.pnml.org/version-2009/grammar/pnmlcoremodel"


def _key(kind, *values):
    return kind + ":" + json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _only(element, name, *, required=False):
    matches = [child for child in element if local(child) == name]
    if len(matches) > 1 or (required and not matches):
        fail(
            FORMAT,
            f"expected {'one' if required else 'at most one'} {name}",
            local(element),
            "invalid_structure",
        )
    return matches[0] if matches else None


def _text(element):
    strict(element, (), ("text", "graphics"), FORMAT)
    value = _only(element, "text", required=True)
    strict(value, (), (), FORMAT)
    return value.text or ""


def _id(element, attr="id"):
    value = element.get(attr)
    if not value or not value.strip():
        fail(FORMAT, f"missing or blank {attr}", local(element), "invalid_id")
    return value


def _graphics(element, ignored):
    allowed = {
        "graphics": (),
        "position": ("x", "y"),
        "dimension": ("x", "y"),
        "offset": ("x", "y"),
        "fill": ("color", "image", "gradient-color", "gradient-rotation"),
        "line": ("shape", "color", "width", "style"),
        "font": (
            "family",
            "style",
            "weight",
            "size",
            "decoration",
            "align",
            "rotation",
        ),
    }
    for graphic in element.iter():
        if local(graphic) != "graphics":
            continue
        strict(graphic, (), set(allowed) - {"graphics"}, FORMAT)
        for child in graphic:
            strict(child, allowed[local(child)], (), FORMAT)
        ignored.append(f"{local(element)}[{element.get('id', '')}]/graphics")


def loads_pnml(payload: bytes | str, *, limits: XMLLimits = XMLLimits()) -> ParsedModel:
    root = parse_xml(payload, FORMAT, limits)
    if root.tag not in ("pnml", f"{{{NAMESPACE}}}pnml"):
        fail(FORMAT, "expected PNML 2009 pnml root", local(root), "invalid_structure")
    namespace = root.tag.removesuffix("pnml")
    for element in root.iter():
        if element.tag != namespace + local(element):
            fail(FORMAT, "foreign XML namespace", element.tag)
    strict(root, (), ("net",), FORMAT)
    net = _only(root, "net", required=True)
    strict(
        net,
        ("id", "type"),
        ("name", "page", "place", "transition", "arc", "finalmarkings"),
        FORMAT,
    )
    if net.get("type") not in (PT_TYPE, CORE_TYPE):
        fail(FORMAT, "only ordinary P/T or core net types are supported", "net@type")
    ids = set()

    def unique(element):
        value = _id(element)
        if value in ids:
            fail(FORMAT, f"duplicate XML ID {value!r}", local(element), "duplicate_id")
        ids.add(value)
        return value

    source_ids = [("net", unique(net))]
    metadata = [("net_type", net.get("type"))]
    ignored = []
    name = _only(net, "name")
    if name is not None:
        metadata.append(("net_name", _text(name)))
        _graphics(name, ignored)
    page = _only(net, "page")
    if page is not None:
        if any(local(child) in ("place", "transition", "arc") for child in net):
            fail(FORMAT, "mixed flat/page net elements", "net", "invalid_structure")
        strict(page, ("id",), ("name", "place", "transition", "arc"), FORMAT)
        source_ids.append(("page", unique(page)))
        page_name = _only(page, "name")
        if page_name is not None:
            metadata.append(("page_name", _text(page_name)))
            _graphics(page_name, ignored)
        container = page
    else:
        metadata.append(("page_mode", "flat"))
        container = net
    places, transitions, arcs, initial = [], [], [], []
    for element in container:
        kind = local(element)
        if kind in ("name", "finalmarkings"):
            continue
        identifier = unique(element)
        if kind == "place":
            strict(element, ("id",), ("name", "initialMarking", "graphics"), FORMAT)
            places.append(Place(identifier))
            initial_element = _only(element, "initialMarking")
            if initial_element is not None:
                value = integer(_text(initial_element), FORMAT, "initialMarking")
                if value:
                    initial.append((identifier, value))
        elif kind == "transition":
            strict(element, ("id",), ("name", "toolspecific", "graphics"), FORMAT)
            tool = _only(element, "toolspecific")
            silent = tool is not None
            if silent:
                strict(tool, ("tool", "version", "activity", "localNodeID"), (), FORMAT)
                if (
                    tool.get("tool") != "ProM"
                    or tool.get("activity") != "$invisible$"
                    or not tool.get("version")
                ):
                    fail(
                        FORMAT,
                        "only explicit ProM invisible transition metadata is supported",
                        "toolspecific",
                    )
                for key in ("version", "localNodeID"):
                    if tool.get(key) is not None:
                        metadata.append(
                            (_key("silent_" + key, identifier), tool.get(key))
                        )
            label = _only(element, "name")
            activity = _text(label) if label is not None else identifier
            try:
                transitions.append(Transition(identifier, None if silent else activity))
            except (TypeError, ValueError) as error:
                fail(FORMAT, str(error), "transition", "invalid_model")
        elif kind == "arc":
            strict(
                element, ("id", "source", "target"), ("inscription", "graphics"), FORMAT
            )
            source, target = _id(element, "source"), _id(element, "target")
            inscription = _only(element, "inscription")
            weight = (
                integer(_text(inscription), FORMAT, "inscription", min=1)
                if inscription is not None
                else 1
            )
            arcs.append(Arc(source, target, weight))
            source_ids.append((_key("arc", source, target), identifier))
        else:
            fail(FORMAT, "unsupported net element", kind)
        if kind in ("place", "transition"):
            name = _only(element, "name")
            if name is not None:
                metadata.append((_key("name", identifier), _text(name)))
        _graphics(element, ignored)
    final_elements = _only(net, "finalmarkings", required=True)
    strict(final_elements, (), ("marking",), FORMAT)
    marking = _only(final_elements, "marking", required=True)
    strict(marking, (), ("place",), FORMAT)
    final, marked = [], set()
    place_ids = {place.id for place in places}
    for element in marking:
        strict(element, ("idref",), ("text",), FORMAT)
        identifier = _id(element, "idref")
        if identifier not in place_ids or identifier in marked:
            fail(
                FORMAT,
                "unknown or duplicate final marking place",
                "finalmarkings/place",
                "invalid_reference",
            )
        marked.add(identifier)
        value = _only(element, "text", required=True)
        strict(value, (), (), FORMAT)
        count = integer(value.text, FORMAT, "finalmarkings/text")
        if count:
            final.append((identifier, count))
    try:
        model = PetriNet(
            tuple(places),
            tuple(transitions),
            tuple(arcs),
            Marking(tuple(initial)),
            Marking(tuple(final)),
        )
    except (TypeError, ValueError) as error:
        fail(FORMAT, str(error), "net", "invalid_model")
    return ParsedModel(
        model,
        FORMAT,
        PROFILE,
        "2009",
        source_digest(payload),
        source_ids=tuple(source_ids),
        metadata=tuple(metadata),
        presentation_ignored=tuple(ignored),
    )


def dumps_pnml(model: PetriNet | ParsedModel) -> bytes:
    imported = model if isinstance(model, ParsedModel) else None
    if imported is not None:
        if (
            imported.format != FORMAT
            or imported.profile != PROFILE
            or imported.format_version != "2009"
            or imported.profile_version != "1.0.0"
        ):
            fail(FORMAT, "wrong import format or profile", code="invalid_model")
        model = imported.model
    if type(model) is not PetriNet:
        raise TypeError("PNML export requires PetriNet or its ParsedModel")
    # Reconstruct to validate forged fields without introducing codec dependencies.
    model = PetriNet(
        tuple(Place(p.id) for p in model.places),
        tuple(Transition(t.id, t.activity) for t in model.transitions),
        tuple(Arc(a.source, a.target, a.weight) for a in model.arcs),
        Marking(model.initial_marking.tokens),
        Marking(model.final_marking.tokens),
    )
    retained = dict(imported.source_ids) if imported else {}
    metadata = dict(imported.metadata) if imported else {}
    if imported is not None:
        expected_ids = {"net", "page"} | {
            _key("arc", arc.source, arc.target) for arc in model.arcs
        }
        expected_metadata = (
            {"net_type", "net_name", "page_mode", "page_name"}
            | {_key("name", item.id) for item in (*model.places, *model.transitions)}
            | {
                _key(kind, transition.id)
                for transition in model.transitions
                if transition.activity is None
                for kind in ("silent_version", "silent_localNodeID")
            }
        )
        if (
            len(retained) != len(imported.source_ids)
            or len(metadata) != len(imported.metadata)
            or not retained.keys() <= expected_ids
            or not metadata.keys() <= expected_metadata
            or any(
                type(value) is not str
                for value in (*retained.values(), *metadata.values())
            )
        ):
            fail(FORMAT, "invalid or duplicate retained metadata", code="invalid_model")
        if metadata.get("page_mode") not in (None, "flat"):
            fail(FORMAT, "invalid retained page mode", code="invalid_model")
        if metadata.get("page_mode") == "flat" and (
            "page" in retained or "page_name" in metadata
        ):
            fail(FORMAT, "flat net cannot retain page metadata", code="invalid_model")
    occupied = {item.id for item in (*model.places, *model.transitions)}

    def identifier(key, fallback):
        value = retained.get(key)
        if value is None:
            value = fallback
            while value in occupied or value in retained.values():
                value += "_"
        if not isinstance(value, str) or not value.strip() or value in occupied:
            fail(FORMAT, "duplicate or invalid retained XML ID", key, "invalid_id")
        occupied.add(value)
        return value

    root = Element("pnml", {"xmlns": NAMESPACE})
    net = SubElement(
        root,
        "net",
        {"id": identifier("net", "pix_net"), "type": metadata.get("net_type", PT_TYPE)},
    )

    def label(parent, name, value):
        SubElement(SubElement(parent, name), "text").text = value

    if "net_name" in metadata:
        label(net, "name", metadata["net_name"])
    if metadata.get("page_mode") == "flat":
        page = net
    else:
        page = SubElement(net, "page", {"id": identifier("page", "pix_page")})
        if "page_name" in metadata:
            label(page, "name", metadata["page_name"])
    initial = dict(model.initial_marking.tokens)
    for place in model.places:
        element = SubElement(page, "place", {"id": place.id})
        if _key("name", place.id) in metadata:
            label(element, "name", metadata[_key("name", place.id)])
        if place.id in initial:
            label(element, "initialMarking", str(initial[place.id]))
    for transition in model.transitions:
        element = SubElement(page, "transition", {"id": transition.id})
        display = (
            transition.activity
            if transition.activity is not None
            else metadata.get(_key("name", transition.id), transition.id)
        )
        label(element, "name", display)
        if transition.activity is None:
            attrs = {
                "tool": "ProM",
                "version": metadata.get(_key("silent_version", transition.id), "6.4"),
                "activity": "$invisible$",
            }
            node_id = metadata.get(_key("silent_localNodeID", transition.id))
            if node_id is not None:
                attrs["localNodeID"] = node_id
            SubElement(element, "toolspecific", attrs)
    for index, arc in enumerate(model.arcs):
        element = SubElement(
            page,
            "arc",
            {
                "id": identifier(
                    _key("arc", arc.source, arc.target), f"pix_arc_{index}"
                ),
                "source": arc.source,
                "target": arc.target,
            },
        )
        if arc.weight != 1:
            label(element, "inscription", str(arc.weight))
    final = SubElement(SubElement(net, "finalmarkings"), "marking")
    for place, count in model.final_marking.tokens:
        SubElement(SubElement(final, "place", {"idref": place}), "text").text = str(
            count
        )
    payload = xml_bytes(root, FORMAT)
    # Catch unsupported retained metadata before the atomic publication wrapper.
    loads_pnml(payload)
    return payload


__all__ = ("loads_pnml", "dumps_pnml")
