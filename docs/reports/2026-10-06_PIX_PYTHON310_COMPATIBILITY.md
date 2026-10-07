# Python 3.10 호환성 반례와 수정

작업: `fix/python310-contracts-20261006`. 기준: `a0688f34e557c885c145051485072fd0623f263f`.
NEXT-04의 최소 지원 버전 실제 실행에서 발견한 제품 결함을 별도 브랜치로 수정했다. `requires-python >=3.10`, package 0.5.0, canonical/projection/result/model version과 dependency/lock은 유지한다.

## 확인된 실패와 변경

첫 Linux Python 3.10.21 전체 실행은 6 failed / 10,544 passed / 40 skipped / 1,169 subtests였다. 이 실행에는 tools-only NEXT-04 회귀 26개가 포함됐다. 이 제품 수정 브랜치는 같은 base에서 별도로 분기했으며 아래 신규 회귀 25개를 포함한다. 따라서 두 실행의 통과 수를 단순 차감해 수정 개수로 읽지 않는다.

| 파일·함수 | 재현된 원인 | 수정과 보존할 경계 |
| --- | --- | --- |
| `case_centric/statistics.py::_summary` | Python 3.10 `pstdev`는 sqrt 이전에 variance를 float로 바꿔 큰 유한 표본에서 overflow | 기존 계산을 먼저 실행하고 OverflowError 때만 exact Fraction 비율로 scale 후 population stddev 복원. 합계·평균·분위수 정의 유지 |
| `event_log/reader.py::_parse_date` | Python 3.10 parser가 허용된 짧은 소수초·6자리 뒤 zero suffix를 거부 | 기존 precision 검사 후 parser 입력만 6자리로 맞춤; XES lexical 원문 보존 |
| `tabular/values.py::timestamp` | 같은 반례가 명시 table mapping에서도 발생 | 같은 precision-safe normalization. nonzero sub-microsecond·offset·timezone 요구는 기존대로 검사 |
| `ocel/ingest/formats/compact.py::_accepts` | inference가 Python 버전별 `fromisoformat` syntax에 의존해 lossy timestamp를 string으로 분류 | calendar만 fraction 없이 정규화해 판별하고 원본 value는 실제 mapping에 넘겨 precision failure 유지 |
| `viewer/visual_contracts.py::ChartPanel` | 허용된 RFC3339 `.1Z`를 Python 3.10이 거부 | 허용 regex 뒤 parser 입력만 pad; 실제 ChartPoint.x·offset·원래 자리수 보존 |

제품 diff는 5개 파일의 34 additions / 8 deletions다. 전체 파일 포맷 변경 없이 관련 줄만 수정했다. 신규 runtime helper·의존성·API는 추가하지 않았다. compact profile의 지원 표준 판본을 바꾼 작업도 아니다.

## 독립 기대값과 회귀

`tests/test_python310_compatibility.py`의 25개 사례는 XES/table의 1~6자리와 zero-tail, chart 원문 보존, compact precision 오류, 큰 표본의 population stddev를 다룬다. timestamp 기대값은 고정 datetime이고 stddev oracle은 Decimal로 직접 중심·제곱합·제곱근을 계산한다. production statistics/firing/alignment를 기대값에 재사용하지 않는다. stddev 비교는 binary64 relative tolerance `1e-15`, absolute tolerance 0이다. 전체 Python minor 간 bitwise 수치 동일성 보장은 아니다.

최초 새 테스트 실행에서 Decimal oracle precision 100이 309자리 정수 표본의 동일값 cancellation까지 보존하지 못해 테스트 자체의 1건 false failure가 있었다. 이 유한 fixture의 제곱까지 충분한 precision 800으로 교정했다. 교정된 **동일 테스트 파일**을 원래 base source에 적용하면 18 failed / 7 passed, 수정 source에서는 25 passed다. 기존 실패 6건의 expectation·skip은 수정하지 않았다.

## 실제 실행

| 검사 | 결과 |
| --- | --- |
| Python 3.10.21 관련 6개 suite + 신규 파일 | 391 passed |
| Python 3.10.21 전체, 수정 branch | **10,549 passed / 40 skipped / 1,169 subtests passed**, JUnit failures=0/errors=0, 196.361초 |
| Python 3.12.14 전체, 수정 branch | **10,549 passed / 40 skipped / 1,169 subtests passed**, stdout 152.47초 |
| 변경 Python 6개 Ruff lint/format | 통과. 최초 wrap 지적 2개 파일만 format 후 확인 |
| 새 wheel build, Python 3.10 별도 core-only venv 설치 | 성공; source 밖 `python -I` import와 설치된 `pix --help` 성공 |
| 수정 checker의 mining / visualization wheel smoke | 각각 success=true, source/wheel/install 249개 파일 bytes 일치 |
| Git diff whitespace | 통과 |

전체 실행은 `python -m pytest tests -q -rs --junitxml=OUT`를 각 interpreter로 실행했다. 두 실행 모두 lock으로 설치한 dev/imports 환경을 사용했다. pytest의 root 설정으로 이 worktree의 src를 사용했으며 baseline 재현은 `-o pythonpath=.../PIX/src`로 원본 경로를 명시했다. 원본 재현과 수정 후 실행은 별도 로그다.

새 wheel SHA-256: `1fad3b4b6107056584c7913bfe8d1eac368aaf81c1dd32a52eb97d8794dd29b4`.
wheel에는 pix만 설치되어 있다. `check_mining_wheel.py`와 `check_visualization_wheel.py`는 별도 NEXT-04 commit `ea82ae1`의 수정 도구를 사용하고 `--source-root`로 이 제품 snapshot을 지정했다. 제품 branch만으로 원래 checker까지 수정됐다고 주장하지 않는다.

[기계 판독 증거](python310-2026-10-06/evidence.json)에 최초·후속 JUnit 요약, 실패 node IDs, 변경 source/test 파일 hash, wheel 대조 결과를 보존했다. source hash는 보고서·evidence 자신의 bytes를 제외하며 전체 staged diff의 자기참조 hash가 아니다.

## 잔여와 유효 범위

40 skip은 browser opt-in 27, Python Playwright 미설치 1, 외부 XES corpus 11, Windows 전용 reparse-point 1이다. Node Playwright Chromium 설치는 ZIP 오류와 후속 lock 오류로 실패해 실제 브라우저는 실행하지 못했다. Windows/macOS, Python 3.13, 외부 corpus, 통합 PR 전체의 NEXT-05 수락은 남아 있다. 기존 3.12 baseline Node UI 통과를 이번 브라우저 실행으로 대신하지 않는다.

이 증거는 명시한 source hash·fixture·환경에 한정한다. 새 timestamp grammar, precision 반례, 수치 오차가 정한 tolerance를 벗어나는 표본, dependency 또는 code 변경 시 해당 경로를 재검증한다. 대규모 성능·전 기능 대체율은 알 수 없음이다. 이번 반례의 수정과 Linux 3.10/3.12 회귀 범위에서는 통과했으며 출시·참조 대체 인증은 별도다.
