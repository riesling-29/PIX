import hashlib

import pytest

import pix._publication as publication
from pix.case_centric.split_miner import SplitBPMN, SplitBPMNFlow, SplitBPMNNode
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.model_io import (
    ModelIOError,
    XMLLimits,
    read_bpmn,
    read_pnml,
    read_ptml,
    write_bpmn,
    write_pnml,
    write_ptml,
)


@pytest.fixture(params=("pnml", "ptml", "bpmn"))
def exchange(request):
    models = {
        "pnml": PetriNet(
            (Place("p"), Place("q")),
            (Transition("t", "A"),),
            (Arc("p", "t"), Arc("t", "q")),
            Marking((("p", 1),)),
            Marking((("q", 1),)),
        ),
        "ptml": ProcessTree(
            "parallel",
            children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
        ),
        "bpmn": SplitBPMN(
            (
                SplitBPMNNode("s", "start_event"),
                SplitBPMNNode("t", "task", "A"),
                SplitBPMNNode("e", "end_event"),
            ),
            (SplitBPMNFlow("f1", "s", "t"), SplitBPMNFlow("f2", "t", "e")),
            "s",
            "e",
        ),
    }
    readers = {"pnml": read_pnml, "ptml": read_ptml, "bpmn": read_bpmn}
    writers = {"pnml": write_pnml, "ptml": write_ptml, "bpmn": write_bpmn}
    kind = request.param
    return kind, models[kind], readers[kind], writers[kind]


def test_public_read_write_returns_evidence_and_roundtrips(exchange, tmp_path):
    kind, model, read, write = exchange
    path = tmp_path / f"model.{kind}"
    published = write(model, path)
    assert published.path == path
    assert published.byte_count == path.stat().st_size
    assert published.output_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    parsed = read(path)
    assert parsed.model == model
    assert parsed.source_sha256 == published.output_sha256
    second = tmp_path / f"second.{kind}"
    write(parsed, second)
    assert read(second).model == model
    assert sorted(read(second).source_ids) == sorted(parsed.source_ids)


def test_no_clobber_is_default_and_explicit_replace_works(exchange, tmp_path):
    kind, model, read, write = exchange
    path = tmp_path / f"model.{kind}"
    path.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        write(model, path)
    assert path.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]
    write(model, path, overwrite=True)
    assert read(path).model == model


def test_bad_model_does_not_replace_original(exchange, tmp_path):
    kind, _, _, write = exchange
    path = tmp_path / f"model.{kind}"
    path.write_bytes(b"original")
    with pytest.raises((TypeError, ValueError)):
        write(object(), path, overwrite=True)
    assert path.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_publication_failure_leaves_original_and_cleans_temporary(
    exchange, tmp_path, monkeypatch
):
    kind, model, _, write = exchange
    path = tmp_path / f"model.{kind}"
    path.write_bytes(b"original")

    def cannot_replace(*args):
        raise OSError("simulated target lock")

    monkeypatch.setattr(publication.os, "replace", cannot_replace)
    with pytest.raises(OSError, match="target lock"):
        write(model, path, overwrite=True)
    assert path.read_bytes() == b"original"
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_file_reader_applies_size_budget(exchange, tmp_path):
    kind, model, read, write = exchange
    path = tmp_path / f"model.{kind}"
    write(model, path)
    with pytest.raises(ModelIOError) as failure:
        read(path, limits=XMLLimits(max_bytes=10))
    assert failure.value.code == "resource_limit"
    assert failure.value.format == kind


@pytest.mark.parametrize(
    "values",
    [
        dict(max_bytes=0),
        dict(max_elements=True),
        dict(max_depth=129),
        dict(max_depth=-1),
    ],
)
def test_limits_are_explicit_positive_bounded_integers(values):
    with pytest.raises(ValueError):
        XMLLimits(**values)
