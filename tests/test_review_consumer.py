import json
from pathlib import Path
from runpy import run_path

from pix.results import result_from_json


def test_version_one_success_does_not_certify_version_two(tmp_path):
    run = run_path(
        str(Path(__file__).resolve().parents[1] / "examples/review_consumer.py")
    )["run_example"]
    a = run(tmp_path / "a")
    b = run(tmp_path / "b", version2_bytes=b"another modification")
    stored = json.loads(
        (tmp_path / "a/consumer-review.json").read_text(encoding="utf-8")
    )
    assert stored["artifacts"][0]["testPassed"] is True
    assert stored["artifacts"][0]["testEventIds"] == ["test-v1"]
    assert stored["artifacts"][1]["testPassed"] is None
    assert stored["artifacts"][1]["testEventIds"] == []
    assert not stored["observation"]["closed"]
    assert a["snapshot"] != b["snapshot"]
    assert a["artifacts"][0] == b["artifacts"][0]
    assert a["artifacts"][1]["sha256"] != b["artifacts"][1]["sha256"]
    result = result_from_json(json.dumps(stored["calculation"]))
    assert result.status.value == "computed"
    assert result.source_digest == stored["projection"]["canonicalSourceDigest"]
