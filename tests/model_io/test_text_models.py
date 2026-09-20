import pytest

from pix.case_centric.powl import POWLNode
from pix.contracts.discovery import ProcessTree
from pix.model_io import (
    ModelIOError,
    TextModelLimits,
    dumps_powl_text,
    dumps_tree_text,
    loads_powl_text,
    loads_tree_text,
)


def test_tree_grammar_and_quoted_labels_do_not_confuse_operators():
    model = loads_tree_text('->("접수", X(tau, "X"), *("검토", "반려"))').model
    assert model.operator == "sequence"
    assert model.children[1].children[1] == ProcessTree("activity", "X")
    assert model.children[2].operator == "loop"
    assert loads_tree_text(dumps_tree_text(model)).model == model
    assert loads_tree_text("'single quoted'").model.activity == "single quoted"


@pytest.mark.parametrize(
    "text",
    ['->("A")', '*("A","B","C")', "tau junk", '__import__("os")', '+("A",)', '""'],
)
def test_invalid_tree_is_rejected(text):
    with pytest.raises(ModelIOError):
        loads_tree_text(text)


def test_powl_partial_order_closure_and_roundtrip():
    text = '{"kind":"partial_order","children":[{"kind":"activity","activity":"A"},{"kind":"activity","activity":"B"},{"kind":"activity","activity":"C"}],"order":[[0,1],[1,2]]}'
    model = loads_powl_text(text).model
    assert model.order == ((0, 1), (0, 2), (1, 2))
    assert loads_powl_text(dumps_powl_text(model)).model == model


@pytest.mark.parametrize(
    "text",
    [
        '{"kind":"tau","kind":"activity"}',
        '{"kind":"tau","oops":true}',
        '{"kind":"partial_order","children":[{"kind":"tau"},{"kind":"tau"}],"order":[[0,1],[1,0]]}',
    ],
)
def test_powl_rejects_duplicate_keys_unknown_fields_and_cycles(text):
    with pytest.raises(ModelIOError):
        loads_powl_text(text)


def test_explicit_limits_for_reads_and_writes():
    with pytest.raises(ModelIOError, match="limit"):
        loads_tree_text('->("A","B")', limits=TextModelLimits(max_nodes=1))
    with pytest.raises(ModelIOError, match="limit"):
        loads_powl_text('{"kind":"tau"}', limits=TextModelLimits(max_bytes=1))
    model = POWLNode("partial_order", children=(POWLNode("tau"), POWLNode("tau")))
    with pytest.raises(ModelIOError, match="width"):
        dumps_powl_text(model, limits=TextModelLimits(max_order_children=1))
