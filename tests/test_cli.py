import json
import subprocess
import sys

from pix.cli import main
from pix.results import read_result


def xes(tmp_path):
    path = tmp_path / "input.xes"
    path.write_text(
        '<log><trace><event><string key="concept:name" value="A"/></event><event><string key="concept:name" value="B"/></event></trace></log>',
        encoding="utf-8",
    )
    return path


def test_inspect_and_ngram_result_publication(tmp_path, capsys):
    path = xes(tmp_path)
    assert main(["inspect", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]
    output = tmp_path / "result.json"
    assert (
        main(
            [
                "ngrams",
                str(path),
                "--n-min",
                "2",
                "--n-max",
                "2",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = read_result(output)
    assert result.value.matrix.columns[0].terms == ("A", "B")
    assert main(["ngrams", str(path), "--output", str(output)]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "error"


def test_partial_evidence_is_not_success_exit(tmp_path, capsys):
    assert main(["ngrams", str(xes(tmp_path)), "--max-evidence", "0"]) == 3
    capsys.readouterr()


def test_agent_acquires_remote_data_and_table_mapping_is_explicit(tmp_path, capsys):
    assert main(["inspect", "https://example.org/log.xes"]) == 2
    assert "Agent" in json.loads(capsys.readouterr().err)["message"]
    path = tmp_path / "records.csv"
    path.write_text("task,action\n1,A\n1,B\n", encoding="utf-8")
    assert main(["dfg", str(path)]) == 2
    capsys.readouterr()
    assert (
        main(["dfg", str(path), "--case-column", "task", "--activity-column", "action"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["computation"]["status"] == "computed"


def test_module_cli_runs_in_real_process(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "pix", "inspect", str(xes(tmp_path))],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["valid"]
