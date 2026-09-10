"""The documented evaluation example produces domain-reviewable real results."""

import json
import os
import subprocess
import sys
from pathlib import Path

from pix.results import read_result


def test_example_reports_joint_execution_rules_and_declared_profiles(tmp_path):
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(
        [
            sys.executable,
            str(root / "examples/model_evaluation.py"),
            "--output",
            str(tmp_path),
        ],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(root / "src")),
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["results"]) == 10
    assert manifest["results"]["open-rules"]["status"] == "partial"
    for name in manifest["results"]:
        result = read_result(tmp_path / f"{name}.json")
        assert result.source_digest == manifest["source_digest"]
    joint = read_result(tmp_path / "joint-alignment.json")
    assert joint.value.cost == 0
    assert joint.value.move_counts.synchronous == 7
    assert joint.value.move_counts.log == 0
    assert joint.value.move_counts.model == 0
    assert read_result(tmp_path / "process-tree.json").spec.algorithm == "pix.im.v1"
    timed = read_result(tmp_path / "closed-rules.json").value.rules[-1]
    assert (timed.fulfilled_count, timed.violated_count, timed.pending_count) == (
        1,
        2,
        0,
    )
    pending = read_result(tmp_path / "open-rules.json").value.rules[0]
    assert (pending.fulfilled_count, pending.violated_count, pending.pending_count) == (
        0,
        0,
        3,
    )
    review = (tmp_path / "review.md").read_text(encoding="utf-8")
    assert "관측되지 않은 중간 수" in review
    assert "## 공동 alignment의 실제 단계" in review
    for name in ("ocdfg", "classical-model", "discovered-ocpn"):
        assert "pixViewerReady" in (tmp_path / f"{name}.html").read_text(
            encoding="utf-8"
        )
