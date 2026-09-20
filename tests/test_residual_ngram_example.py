from pathlib import Path
from runpy import run_path


def test_review_is_reproducible_and_exposes_false_cross_object_pattern(tmp_path):
    module = run_path(
        str(Path(__file__).parents[1] / "examples/residual_ngram_review.py")
    )
    summary = module["write_review"](tmp_path)
    assert summary["count"]["occurrences"] == 27
    assert summary["separate-objects"]["columns"] == 0
    assert summary["wrong-global-order"]["columns"] == 1
    assert (tmp_path / "ngram-review.html").exists()
    before = (tmp_path / "count.json").read_bytes()
    assert module["write_review"](tmp_path) == summary
    assert (tmp_path / "count.json").read_bytes() == before
