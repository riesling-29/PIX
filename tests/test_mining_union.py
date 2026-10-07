"""Cross-domain public API scenarios; independent hand-counted expectations."""

import ast
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pix import case_centric as cc
from pix import object_centric as oc
from pix._mining_registry import mining_schemas
from pix.case_centric._input import as_case_traces
from pix.compute.conformance import align_traces as legacy_align
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.replay import replay_traces as legacy_replay
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType
from pix.results import result_from_json, result_json_bytes


def case_log():
    # Source order B,A is deliberate; timestamps also contradict source order.
    origin = datetime(2026, 9, 15, tzinfo=timezone.utc)
    return CaseLog(
        (
            CaseTrace(
                "case-1",
                tuple(
                    CaseEvent(
                        f"event-{i}",
                        (
                            CaseAttribute("concept:name", "string", label),
                            CaseAttribute(
                                "time:timestamp", "date", origin - timedelta(seconds=i)
                            ),
                        ),
                    )
                    for i, label in enumerate(("B", "A"))
                ),
            ),
        )
    )


def object_log():
    # Three events, four unique participations and five qualified relations.
    origin = datetime(2026, 9, 15, tzinfo=timezone.utc)
    return OCEL(
        event_types=(EventType("open"), EventType("joint"), EventType("finish")),
        object_types=(ObjectType("order"), ObjectType("item")),
        events=tuple(
            Event(f"e{i}", label, origin + timedelta(seconds=i))
            for i, label in enumerate(("open", "joint", "finish"))
        ),
        objects=(Object("o", "order"), Object("i", "item")),
        e2o=(
            E2O("e0", "o", "flow"),
            E2O("e1", "o", "flow"),
            E2O("e1", "o", "audit"),
            E2O("e1", "i", "flow"),
            E2O("e2", "i", "flow"),
        ),
        o2o=(O2O("o", "i", "contains"),),
    )


@pytest.mark.parametrize("domain", [cc, oc])
def test_public_namespace_exports_resolve(domain):
    assert len(domain.__all__) == len(set(domain.__all__))
    for name in domain.__all__:
        assert getattr(domain, name) is not None
        assert name in dir(domain)
    with pytest.raises(AttributeError):
        getattr(domain, "not_a_registered_module")


@pytest.mark.parametrize("domain", [cc, oc])
def test_implemented_result_modules_have_public_and_persistence_registration(domain):
    """A working new algorithm must not silently miss the storage allowlist."""
    registered = mining_schemas()
    for file in Path(domain.__file__).parent.glob("*.py"):
        syntax = ast.parse(file.read_text(encoding="utf-8"))
        declares_schema = any(
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "RESULT_SCHEMAS"
                for target in node.targets
            )
            or isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RESULT_SCHEMAS"
            for node in syntax.body
        )
        if not declares_schema:
            continue
        assert file.stem in domain.__all__, file.name
        module = importlib.import_module(f"{domain.__name__}.{file.stem}")
        assert isinstance(module.RESULT_SCHEMAS, dict), file.name
        for operator, schema in module.RESULT_SCHEMAS.items():
            assert registered.get(operator) == schema, operator


def test_case_pipeline_preserves_source_order_and_legacy_identity():
    log = case_log()
    traces = cc.case_traces(log)
    graph = cc.discover_dfg(log)
    assert [(e.source, e.target, e.count) for e in graph.value.edges] == [("B", "A", 1)]
    tree = cc.discover_inductive(log)
    assert tree.value.operator == "sequence"
    assert tuple(node.activity for node in tree.value.children) == ("B", "A")
    net = process_tree_to_petri_net(tree.value)
    aligned = cc.align_traces(log, net)
    replayed = cc.replay_traces(log, net)
    assert aligned == legacy_align(traces, net)
    assert replayed == legacy_replay(traces, net)
    assert as_case_traces(traces) is traces
    for result in (graph, tree, aligned, replayed):
        assert result.source_digest == traces.source_digest
        assert result_from_json(result_json_bytes(result)) == result


def test_existing_projection_cannot_silently_change_classifier():
    traces = cc.case_traces(case_log())
    with pytest.raises(ValueError, match="re-project"):
        as_case_traces(traces, cc.CaseTraceSpec(activity_key="another:name"))
    with pytest.raises(TypeError, match="CaseLog"):
        as_case_traces(traces.value)


def test_object_pipeline_counts_shared_events_once_and_preserves_qualifiers():
    log = object_log()
    ctx = oc.ComputationContext(log)
    result = oc.object_statistics(ctx)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.source_event_count == 3
    assert result.value.unique_participation_count == 4
    assert result.value.e2o_relation_count == 5
    assert result.value.qualifier_relation_counts == (("audit", 1), ("flow", 4))
    assert ctx.log.o2o == log.o2o
    assert result_from_json(result_json_bytes(result)) == result
    # Projections require an explicit object type; joint event appears in each.
    order = oc.reconstruct_traces(ctx, oc.TraceSpec(object_type="order"))
    item = oc.reconstruct_traces(ctx, oc.TraceSpec(object_type="item"))
    assert sum(len(t.events) for t in order.value.traces + item.value.traces) == 4
    assert result.value.source_event_count == 3


def test_case_and_object_inputs_are_not_implicitly_interchanged():
    with pytest.raises(TypeError):
        cc.discover_dfg(object_log())
    with pytest.raises((TypeError, AttributeError)):
        oc.ComputationContext(case_log())
