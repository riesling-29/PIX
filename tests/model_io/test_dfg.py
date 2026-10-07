import pytest

from pix.case_centric.discovery import RelationDiscoverySpec, discover_dfg
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.model_io import (
    DFGFile,
    ModelIOError,
    dumps_dfg,
    loads_dfg,
    project_dfg_exchange,
    read_dfg,
    write_dfg,
)

GOLDEN = b"3\nA\nB\nIsolated\n2\n0x2\n2x1\n2\n1x2\n2x1\n0>1x2\n"


def test_independent_classic_fixture_preserves_isolated_activity_and_counts(tmp_path):
    model = loads_dfg(GOLDEN).model
    assert model.activities == ("A", "B", "Isolated")
    assert model.edges == (("A", "B", 2),)
    assert model.start_counts == (("A", 2), ("Isolated", 1))
    assert dumps_dfg(model) == GOLDEN
    path = tmp_path / "example.dfg"
    write_dfg(model, path)
    assert read_dfg(path).model == model
    with pytest.raises(FileExistsError):
        write_dfg(model, path)


def test_explicit_projection_documents_unrepresentable_information():
    log = CaseLog(
        (
            CaseTrace(
                "t", (CaseEvent("a", (CaseAttribute("concept:name", "string", "A"),)),)
            ),
            CaseTrace("empty"),
        )
    )
    projected = project_dfg_exchange(discover_dfg(log))
    assert "empty_trace_count" in projected.omitted_information
    assert loads_dfg(dumps_dfg(projected.model)).model.activities == ("A",)
    with pytest.raises(ValueError, match="occurrence"):
        project_dfg_exchange(discover_dfg(log, RelationDiscoverySpec(counting="cases")))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "1\nA\n",
        "1\nA\n1\n-1x2\n0\n",
        "1\nA\n0\n0\n0>2x1\n",
        "2\nA\nA\n0\n0\n",
        "1\nA\n0\n0\n0>0x0\n",
        "1\nA\n0\n0\n0>0x1\n0>0x2\n",
        "1\n A\n0\n0\n",
    ],
)
def test_invalid_or_ambiguous_documents_are_rejected(text):
    with pytest.raises(ModelIOError):
        loads_dfg(text)


def test_byte_budget_and_empty_graph():
    with pytest.raises(ModelIOError, match="limit"):
        loads_dfg(GOLDEN, max_bytes=3)
    assert loads_dfg(dumps_dfg(DFGFile((), (), (), ()))).model == DFGFile(
        (), (), (), ()
    )
