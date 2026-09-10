"""The documented example produces independently readable native artifacts."""

import os
import subprocess
import sys
from pathlib import Path

from pix.compute.model_semantics import fire_binding, is_object_final
from pix.contracts.models import Binding
from pix.models import read_model
from pix.results import read_result


def test_executable_example_and_no_overwrite(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, PYTHONPATH=str(root / "src"))
    command = [
        sys.executable,
        str(root / "examples" / "native_pipeline.py"),
        "--output",
        str(tmp_path),
    ]
    run = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    assert all(
        (tmp_path / name).is_file()
        for name in (
            "ocel.json",
            "ocel.xml",
            "ocel.sqlite",
            "process.html",
            "model.html",
            "ocpn.html",
        )
    )
    discovered = read_model(tmp_path / "model.json")
    assert discovered.origin == "discovered"
    results = [
        read_result(path)
        for path in tmp_path.glob("*.json")
        if path.name not in ("ocel.json", "model.json", "provided-ocpn.json")
    ]
    assert len(results) == 8
    assert all(result.status.value == "computed" for result in results)
    assert discovered.source_computation_id in {
        result.computation_id for result in results
    }
    supplied = read_model(tmp_path / "provided-ocpn.json")
    assert supplied.origin == "provided"
    assert supplied.source_computation_id is None
    binding = Binding("ship", (("Order", ("O1", "O2")), ("Package", ("P1",))))
    marking = fire_binding(supplied.model, supplied.model.initial_marking, binding)
    assert is_object_final(supplied.model, marking)
    original = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    retry = subprocess.run(
        command, cwd=tmp_path, env=environment, capture_output=True, text=True
    )
    assert retry.returncode != 0
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == original
