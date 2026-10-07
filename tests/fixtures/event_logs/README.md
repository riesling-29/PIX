# Sample event logs

Place event-log files used by PIX tests in this directory.

Keep downloaded fixtures unmodified where possible, and record each file's
source URL, version or retrieval date, and license before committing it. Do not
store private, sensitive, or proprietary logs here.

## Local XES corpus (2026-09-13)

Active test inputs are organized below; the downloaded ZIPs and original user
extraction directories remain unchanged. Tests select only the `logs` directories.

```text
xes/
  manifest.json
  activities_daily_living/
    logs/       8 distinct .xes.gz logs
    source/     supplied README
  hospital_billing/
    logs/       one log as both .xes.gz and .xes
    source/     supplied DATA.xml and readme
```

There are nine independent logs and ten physical test files. The standalone
Hospital gzip download is identical to the gzip inside its ZIP. The organized
Hospital plain XES is byte-identical to the decompressed gzip. `xes/manifest.json`
records paths, sizes, SHA-256 and current validation status. Data and this manifest
remain ignored by Git; this README and test code are tracked separately.

The opt-in `tests/event_log/test_downloaded_xes.py` checks all ten physical files
against the full source XML and checks gzip/plain equality (11 tests). It checks
source counts and metadata, then verifies source-order projections and every
declared classifier. Discovery/replay uses at most 32 complete traces and 4,096
events per file, explicitly reported as a sample.
Run in a Python environment permitted by the machine's application policy:

```powershell
$env:PIX_RUN_XES_CORPUS = '1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest tests/event_log/test_downloaded_xes.py -q --junitxml=.artifacts/xes-corpus-2026-09-13/pytest.xml
Remove-Item Env:PIX_RUN_XES_CORPUS
Remove-Item Env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
```

On 2026-09-13 these **11 tests passed in 138.94 seconds**; the existing 92 event-log
regression tests also passed. Hospital's 100,000 traces / 451,359 events / 18
activities were independently counted from XML and matched both PIX imports.
All imports and full-source comparisons passed. At the test's 256-marking silent
search limit, `edited_hh102_weekends` returned partial replay (0 completed / 7
limited). A separate 1,024-marking follow-up completed all seven traces with zero
missing/remaining tokens. These are explicitly scoped analysis results, not
full-log fitness measurements for Hospital or HH104 labour.

The original `.venv` launcher remains blocked. The successful run used the
official, signature-verified Python 3.13.15 embeddable package at
`.artifacts/xes-corpus-2026-09-13/runtime/python-3.13.15-embed-amd64/python.exe`.
Its local `python313._pth` explicitly includes this checkout's `src` and the
existing pure-Python pytest dependency directory. System security settings and
PATH were not changed. Substitute this executable for `python` above to rerun
in the prepared local environment. Runtime provenance and per-file results are
under `.artifacts/xes-corpus-2026-09-13/` and remain ignored by Git.

See [the detailed validation report](../../../docs/version/v0.5.0_XES_CORPUS_2026-09-13.md)
for per-log counts, replay scope and limitations.
