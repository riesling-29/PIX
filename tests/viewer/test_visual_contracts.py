"""Semantic identity and hostile-input boundaries for native visual documents."""

from __future__ import annotations

import json
import math
from dataclasses import FrozenInstanceError, replace

import pytest

from pix.viewer.visual_contracts import (
    ChartPanel,
    ChartPoint,
    ChartSeries,
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    TimelineItem,
    TimelineLane,
    TimelinePanel,
    VisualEdge,
    VisualField,
    VisualizationDocument,
    VisualMetric,
    VisualNode,
    VisualProvenance,
)
from pix.viewer.visual_serialization import (
    dumps_visualization,
    loads_visualization,
    visual_from_dict,
    visual_to_dict,
)


def _document() -> VisualizationDocument:
    return VisualizationDocument(
        "PIX 측정과 모델",
        (
            GraphPanel(
                "net",
                "Same labels, separate transitions",
                (
                    VisualNode(
                        "t1",
                        "Approve",
                        "transition",
                        "order",
                        (VisualMetric("frequency", 2, "events"),),
                    ),
                    VisualNode(
                        "t2",
                        "Approve",
                        "transition",
                        "item",
                        (VisualMetric("frequency", None, "events"),),
                    ),
                ),
                (
                    VisualEdge(
                        "e1",
                        "t1",
                        "t2",
                        "relation",
                        "qualifier",
                        True,
                        (VisualMetric("duration", 1.0, "seconds"),),
                        (VisualField("qualifier", "item"),),
                    ),
                    VisualEdge("e2", "t2", "t1", directed=False),
                ),
                "bipartite",
                "Counts do not imply soundness.",
            ),
            MatrixPanel(
                "footprints",
                "Observed footprint",
                ("A", "B"),
                ("A", "B"),
                (
                    MatrixCell("A", "B", "→", "causal"),
                    MatrixCell("B", "A", None, "unknown"),
                ),
                (
                    VisualField(
                        "→", "observed directly-follows only in this direction"
                    ),
                    VisualField("unknown", "not evaluated; not zero"),
                ),
            ),
            ChartPanel(
                "chart",
                "Duration",
                "line",
                (
                    ChartSeries(
                        "actual",
                        (
                            ChartPoint("2026-09-15T09:00:00+09:00", 3),
                            ChartPoint("2026-09-15T00:00:01Z", None),
                        ),
                    ),
                ),
                "time",
                "Event time",
                "Duration",
                None,
                "seconds",
            ),
            TimelinePanel(
                "trace",
                "Shared event appearances",
                (TimelineLane("o1", "Order"), TimelineLane("o2", "Item")),
                (
                    TimelineItem(
                        "e/o1",
                        "o1",
                        1,
                        1,
                        "Pack",
                        details=(VisualField("event_id", "shared-e"),),
                    ),
                    TimelineItem(
                        "e/o2",
                        "o2",
                        1.0,
                        None,
                        "Pack",
                        status="open",
                        details=(VisualField("event_id", "shared-e"),),
                    ),
                ),
                "timestamp",
                "seconds",
            ),
            TablePanel(
                "table",
                "Typed scalar evidence",
                (
                    "null",
                    "bool",
                    "int",
                    "float",
                    "text",
                    "negative zero",
                    "large integer",
                ),
                ((None, True, 1, 1.0, "1", -0.0, 2**100),),
            ),
        ),
        (
            VisualProvenance(
                "calc:1",
                "source:abc",
                "model:xyz",
                "pix.example",
                "incomplete",
                (VisualField("source order", True),),
            ),
        ),
        ("One alignment remains unresolved.",),
        "partial",
    )


def test_all_panel_types_roundtrip_without_type_or_identity_loss():
    original = _document()
    restored = loads_visualization(dumps_visualization(original))
    assert restored == original
    assert [type(v) for v in restored.panels[-1].rows[0]] == [
        type(None),
        bool,
        int,
        float,
        str,
        float,
        int,
    ]
    assert math.copysign(1, restored.panels[-1].rows[0][5]) == -1
    assert restored.panels[0].nodes[0].id != restored.panels[0].nodes[1].id
    assert restored.panels[0].nodes[0].label == restored.panels[0].nodes[1].label
    assert restored.panels[3].items[1].end is None
    assert restored.provenance[0].status == "incomplete"


def test_deterministic_json_is_independent_of_dictionary_key_order():
    original = _document()
    data = visual_to_dict(original)
    reordered = dict(reversed(tuple(data.items())))
    assert dumps_visualization(visual_from_dict(reordered)) == dumps_visualization(
        original
    )
    assert (
        loads_visualization(dumps_visualization(original, indent=2).encode("utf-8"))
        == original
    )


def test_dict_is_an_independent_mutable_copy():
    original = _document()
    data = visual_to_dict(original)
    data["panels"][0]["nodes"][0]["label"] = "edited"
    assert original.panels[0].nodes[0].label == "Approve"


def test_frozen_instance_rejects_mutation():
    node = VisualNode("a", "A")
    with pytest.raises(FrozenInstanceError):
        node.label = "B"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize(
    "factory",
    [
        lambda v: VisualField("x", v),
        lambda v: VisualMetric("x", v, "count"),
        lambda v: ChartPoint(v, 1),
        lambda v: ChartPoint(1, v),
        lambda v: TimelineItem("a", "l", v, None),
    ],
)
def test_nonfinite_numbers_are_never_serializable(value, factory):
    with pytest.raises(ValueError, match="finite"):
        factory(value)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VisualMetric("x", True, "count"),
        lambda: ChartPoint(True, 1),
        lambda: ChartPoint(1, False),
        lambda: TimelineItem("x", "l", True, 2),
        lambda: TimelineItem("x", "l", 1, False),
    ],
)
def test_booleans_are_not_geometry_or_measurements(factory):
    with pytest.raises(TypeError, match="number"):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VisualField("", 1),
        lambda: VisualMetric("metric", 1, " "),
        lambda: VisualNode(" ", "A"),
        lambda: VisualNode(
            "n", "A", details=(VisualField("x", 1), VisualField("x", 2))
        ),
        lambda: VisualNode(
            "n",
            "A",
            metrics=(VisualMetric("x", 1, "events"), VisualMetric("x", 2, "objects")),
        ),
        lambda: GraphPanel("g", "G", (VisualNode("a", "A"), VisualNode("a", "B"))),
        lambda: GraphPanel(
            "g", "G", (VisualNode("a", "A"),), (VisualEdge("e", "a", "missing"),)
        ),
        lambda: GraphPanel(
            "g",
            "G",
            (VisualNode("a", "A"),),
            (VisualEdge("e", "a", "a"), VisualEdge("e", "a", "a")),
        ),
        lambda: GraphPanel("g", "G", layout="graphviz"),
        lambda: GraphPanel(
            "g",
            "G",
            (
                VisualNode("a", "A", metrics=(VisualMetric("rate", 1, "events"),)),
                VisualNode("b", "B", metrics=(VisualMetric("rate", 1, "objects"),)),
            ),
        ),
        lambda: MatrixPanel("m", "M", ("a", "a"), ("b",)),
        lambda: MatrixPanel(
            "m",
            "M",
            ("a",),
            ("b",),
            (MatrixCell("missing", "b", 1),),
            (VisualField("value", "count"),),
        ),
        lambda: MatrixPanel("m", "M", ("a",), ("b",), (MatrixCell("a", "b", 1),)),
        lambda: MatrixPanel(
            "m",
            "M",
            ("a",),
            ("b",),
            (MatrixCell("a", "b", 1), MatrixCell("a", "b", 2)),
            (VisualField("value", "count"),),
        ),
        lambda: ChartPanel("c", "C", "pie"),
        lambda: ChartPanel("c", "C", "line", (ChartSeries("s"), ChartSeries("s"))),
        lambda: ChartPanel(
            "c",
            "C",
            "line",
            (ChartSeries("s", (ChartPoint("2026-09-15T00:00:00", 1),)),),
            x_type="time",
        ),
        lambda: ChartPanel(
            "c",
            "C",
            "line",
            (ChartSeries("s", (ChartPoint("garbage", 1),)),),
            x_type="time",
        ),
        lambda: TimelineItem("i", "lane", 2, 1),
        lambda: TimelinePanel(
            "t", "T", (TimelineLane("l", "L"), TimelineLane("l", "L"))
        ),
        lambda: TimelinePanel("t", "T", items=(TimelineItem("i", "missing", 0, None),)),
        lambda: TimelinePanel(
            "t",
            "T",
            (TimelineLane("l", "L"),),
            (TimelineItem("i", "l", 0, 0), TimelineItem("i", "l", 1, 1)),
        ),
        lambda: TimelinePanel("t", "T", axis_type="timestamp", unit="milliseconds"),
        lambda: TablePanel("t", "T", ("x", "x")),
        lambda: TablePanel("t", "T", ("x",), ((1, 2),)),
        lambda: VisualizationDocument(
            "V", (GraphPanel("p", "P"), TablePanel("p", "P", ()))
        ),
        lambda: VisualizationDocument("V", status="verified"),
    ],
)
def test_invalid_semantics_raise_without_silent_merges_or_repairs(factory):
    with pytest.raises(ValueError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VisualField("x", {}),
        lambda: VisualField("x", object()),
        lambda: VisualNode("n", "N", details=[VisualField("x", 1)]),
        lambda: GraphPanel("g", "G", nodes=[VisualNode("n", "N")]),
        lambda: GraphPanel("g", "G", nodes=(object(),)),
        lambda: VisualEdge("e", "a", "b", directed=1),
        lambda: ChartPanel("c", "C", "bar", (ChartSeries("s", (ChartPoint(1, 1),)),)),
        lambda: ChartPanel(
            "c", "C", "bar", (ChartSeries("s", (ChartPoint("1", 1),)),), x_type="number"
        ),
        lambda: TablePanel("t", "T", ("x",), ([1],)),
        lambda: TablePanel("t", "T", ("x",), (({"nested": 1},),)),
        lambda: VisualizationDocument("V", panels=(object(),)),
        lambda: VisualizationDocument("V", issues=["mutable"]),
    ],
)
def test_mutable_or_wrong_typed_fields_are_rejected(factory):
    with pytest.raises(TypeError):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: VisualField("x", "\ud800"),
        lambda: VisualNode("a", "\udfff"),
        lambda: ChartPoint("\ud800", 1),
        lambda: VisualizationDocument("V", issues=("\ud800",)),
    ],
)
def test_invalid_unicode_is_rejected_at_construction(factory):
    with pytest.raises(ValueError, match="surrogates"):
        factory()


@pytest.mark.parametrize("status", ["ok", "partial", "unsupported", "error"])
def test_empty_document_can_explain_unsupported_or_failed_calculation(status):
    original = VisualizationDocument(
        "No inferred panel", issues=("Source has no result payload.",), status=status
    )
    assert loads_visualization(dumps_visualization(original)) == original


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema":"pix.visualization.v1","schema":"pix.visualization.v1"}',
        '{"panels":[{"kind":"graph","kind":"table"}]}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":-Infinity}',
        "[]",
        "null",
        "true",
        "42",
        '"__import__(\\"os\\")"',
        '{"__class__":"VisualizationDocument"}',
        '{"schema":"pix.visualization.v2"}',
        "{bad json}",
    ],
)
def test_hostile_or_incomplete_json_has_no_permissive_fallback(payload):
    with pytest.raises((ValueError, TypeError)):
        loads_visualization(payload)


def test_unknown_nested_keys_and_panel_types_are_rejected():
    data = visual_to_dict(_document())
    data["panels"][0]["nodes"][0]["onclick"] = "alert(1)"
    with pytest.raises(ValueError, match="unknown"):
        visual_from_dict(data)
    data = visual_to_dict(_document())
    data["panels"][0]["kind"] = "python.module.Class"
    with pytest.raises(ValueError, match="unsupported"):
        visual_from_dict(data)


@pytest.mark.parametrize(
    "field,value", [("value", True), ("value", float("inf")), ("unit", None)]
)
def test_json_measurements_revalidate_scalar_semantics(field, value):
    data = visual_to_dict(_document())
    data["panels"][0]["nodes"][0]["metrics"][0][field] = value
    with pytest.raises((ValueError, TypeError)):
        visual_from_dict(data)


def test_json_overflow_number_is_not_accepted_as_finite():
    data = visual_to_dict(_document())
    text = json.dumps(data).replace('"value": 2', '"value": 1e400', 1)
    with pytest.raises(ValueError, match="finite"):
        loads_visualization(text)


def test_labels_remain_literal_data_and_never_execute():
    text = '</script><script>throw new Error("never run")</script>'
    original = VisualizationDocument(
        text, (TablePanel("t", "T", ("literal",), ((text,),)),)
    )
    assert (
        loads_visualization(dumps_visualization(original)).panels[0].rows[0][0] == text
    )


def test_byte_budget_checks_utf8_size_and_can_be_explicitly_raised():
    text = dumps_visualization(VisualizationDocument("한국어"))
    size = len(text.encode("utf-8"))
    with pytest.raises(ValueError, match="max_bytes"):
        loads_visualization(text, max_bytes=size - 1)
    assert loads_visualization(text, max_bytes=size).title == "한국어"
    with pytest.raises(ValueError, match="max_bytes"):
        loads_visualization(text.encode("utf-8"), max_bytes=size - 1)


@pytest.mark.parametrize("budget", [True, 0, -1, 1.5])
def test_invalid_budgets_are_rejected(budget):
    with pytest.raises(ValueError, match="positive integer"):
        loads_visualization("{}", max_bytes=budget)


@pytest.mark.parametrize("payload", [b"\xff", "\ud800"])
def test_invalid_utf8_is_rejected(payload):
    with pytest.raises(ValueError, match="UTF-8"):
        loads_visualization(payload)


def test_excessive_json_nesting_has_controlled_error():
    with pytest.raises(ValueError, match="nested"):
        loads_visualization("[" * 10000 + "0" + "]" * 10000)


def test_forged_frozen_instances_are_revalidated_on_write():
    document = VisualizationDocument("V", (GraphPanel("g", "G"),))
    object.__setattr__(document.panels[0], "layout", "graphviz")
    with pytest.raises(ValueError, match="layout"):
        dumps_visualization(document)
    object.__setattr__(document, "schema", "pix.visualization.v0")
    with pytest.raises(ValueError):
        dumps_visualization(document)


def test_non_document_objects_are_not_arbitrarily_encoded():
    with pytest.raises(TypeError, match="VisualizationDocument"):
        dumps_visualization({"title": "not a contract"})
    with pytest.raises(TypeError, match="str or UTF-8 bytes"):
        loads_visualization(bytearray(b"{}"))


@pytest.mark.parametrize("indent", [True, -1, 9, "2"])
def test_invalid_json_indent_is_explicit(indent):
    with pytest.raises(ValueError, match="indent"):
        dumps_visualization(VisualizationDocument("V"), indent=indent)


def test_replace_is_validated_and_does_not_mutate_parent():
    original = _document()
    with pytest.raises(ValueError, match="unique"):
        replace(original, panels=original.panels + (original.panels[0],))
    assert len(original.panels) == 5


def test_non_string_dictionary_keys_do_not_trigger_arbitrary_conversion():
    class BadKey:
        def __str__(self):
            raise AssertionError("must not call untrusted __str__")

    with pytest.raises(TypeError, match="keys"):
        visual_from_dict({BadKey(): 1})


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-15T09:00:00Z",
        "2026-09-15T09:00:00+09:00",
        "2026-09-15T09:00:00-05:30",
        "2026-09-15T09:00:00.1Z",
        "2026-09-15T09:00:00.123Z",
        "2026-09-15T09:00:00.123456+09:00",
        "2024-02-29T23:59:59.000001+00:00",
        "0001-01-01T00:00:00Z",
        "9999-12-31T23:59:59Z",
    ],
)
def test_time_chart_rfc3339_strings_retain_original_offset_and_precision(timestamp):
    panel = ChartPanel(
        "time",
        "Timestamps",
        "scatter",
        (ChartSeries("observations", (ChartPoint(timestamp, 1),)),),
        x_type="time",
    )
    restored = loads_visualization(
        dumps_visualization(VisualizationDocument("V", (panel,)))
    )
    assert restored.panels[0].series[0].points[0].x == timestamp


@pytest.mark.parametrize(
    "timestamp",
    [
        "20260915T090000Z",
        "2026-W38-2T09:00:00Z",
        "2026-09-15 09:00:00Z",
        "2026-09-15X09:00:00Z",
        "2026-09-15t09:00:00Z",
        "2026-09-15T09:00:00z",
        "2026-09-15T09:00Z",
        "2026-09-15T09Z",
        "2026-09-15T09:00:00",
        "2026-09-15T09:00:00+0900",
        "2026-09-15T09:00:00+09",
        "2026-09-15T09:00:00+09:00:01",
        "2026-09-15T09:00:00+09:00:00.1",
        "2026-09-15T09:00:00,123Z",
        "2026-09-15T09:00:00.1234567Z",
        "2026-09-15T09:00:00.Z",
        "2026-09-15T09:00:00Z\n",
        "２０２６-09-15T09:00:00Z",
        "2026-02-29T09:00:00Z",
        "2026-09-15T24:00:00Z",
        "2026-09-15T09:00:60Z",
        "2026-09-15T09:00:00+24:00",
        "2026-09-15T09:00:00+00:60",
        "2026-09-15T09:00:00+09:99",
        "0000-01-01T00:00:00Z",
    ],
)
def test_time_chart_rejects_python_only_or_invalid_timestamp_forms(timestamp):
    with pytest.raises(ValueError, match="time chart x"):
        ChartPanel(
            "time",
            "Timestamps",
            "line",
            (ChartSeries("observations", (ChartPoint(timestamp, 1),)),),
            x_type="time",
        )


def test_escaped_json_surrogate_is_rejected_after_json_decoding():
    data = visual_to_dict(_document())
    data["panels"][4]["rows"][0][4] = "\ud800"
    # The transport itself is valid ASCII; the invalid scalar only appears
    # after json.loads expands its escape, and contract validation must reject it.
    encoded = json.dumps(data, ensure_ascii=True)
    encoded.encode("utf-8")
    with pytest.raises(ValueError, match="surrogates"):
        loads_visualization(encoded)


def test_scoped_provenance_retains_nested_input_ownership_in_json():
    document = VisualizationDocument(
        "Composed evidence",
        (
            GraphPanel("input-0/net", "Model"),
            TablePanel("input-1/input-0/rows", "Observations", ("event",)),
        ),
        (
            VisualProvenance(
                model_digest="model:abc",
                panel_ids=("input-0/net",),
                input_path=(0,),
            ),
            VisualProvenance(
                calculation_id="calc:xyz",
                source_digest="source:xyz",
                panel_ids=("input-1/input-0/rows",),
                input_path=(1, 0),
            ),
            VisualProvenance(status="failed", input_path=(1, 1)),
        ),
    )
    encoded = visual_to_dict(document)
    assert encoded["provenance"][1]["panel_ids"] == ["input-1/input-0/rows"]
    assert encoded["provenance"][1]["input_path"] == [1, 0]
    restored = loads_visualization(dumps_visualization(document))
    assert restored == document
    assert restored.provenance[2].panel_ids == ()
    assert restored.provenance[2].input_path == (1, 1)


def test_provenance_existing_positional_arguments_remain_compatible():
    source = VisualProvenance(
        "c", "s", "m", "o", "partial", (VisualField("note", True),)
    )
    assert source.details == (VisualField("note", True),)
    assert source.panel_ids == ()
    assert source.input_path == ()
    assert loads_visualization(
        dumps_visualization(VisualizationDocument("V", provenance=(source,)))
    ).provenance == (source,)


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"panel_ids": ("a", "a")}, ValueError),
        ({"panel_ids": (" ",)}, ValueError),
        ({"panel_ids": ("\ud800",)}, ValueError),
        ({"panel_ids": ["a"]}, TypeError),
        ({"panel_ids": (1,)}, TypeError),
        ({"input_path": (-1,)}, ValueError),
        ({"input_path": (True,)}, TypeError),
        ({"input_path": (0.0,)}, TypeError),
        ({"input_path": [0]}, TypeError),
    ],
)
def test_provenance_scope_and_input_path_are_strict(kwargs, error):
    with pytest.raises(error):
        VisualProvenance(**kwargs)


def test_provenance_cannot_claim_an_absent_document_panel():
    with pytest.raises(ValueError, match="reference document panels"):
        VisualizationDocument(
            "V",
            (GraphPanel("actual", "A"),),
            (VisualProvenance(panel_ids=("missing",)),),
        )


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("panel_ids", ["missing"], ValueError),
        ("panel_ids", ["net", "net"], ValueError),
        ("input_path", [True], TypeError),
        ("input_path", [-1], ValueError),
        ("input_path", "0/1", TypeError),
    ],
)
def test_json_provenance_scope_and_path_do_not_bypass_validation(field, value, error):
    data = visual_to_dict(_document())
    data["provenance"][0][field] = value
    with pytest.raises(error):
        loads_visualization(json.dumps(data))
