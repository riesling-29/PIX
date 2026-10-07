# NEXT-04 wheel 의존성 계약 수정과 환경 검증

기준: `a0688f34e557c885c145051485072fd0623f263f`.
작업: `ci/wheel-contract-20261006`. 제품 코드·`pyproject.toml`·`uv.lock`·지원 Python 하한은 변경하지 않았다.

## 재현과 수정

앞선 Linux/Python 3.12.14 wheel 검사에서 `tzdata>=2024.1; sys_platform == "win32"`를 unconditional dependency로 취급하여 `The native wheel unexpectedly requires a runtime dependency`로 중단했다. 같은 가정이 `check_native_wheel.py`에도 있었다.

공유 stdlib helper `tools/check_wheel_environment.py`를 추가했다. 현재 pyproject가 생성하는 단일 Windows tzdata 선언과 명시적 extra-only marker만 인정한다. 일반 PEP 508 evaluator가 아니다. 임의 core dependency·marker 변경·extra OR를 이용한 active dependency 우회는 거부한다. Windows 설치 목록은 pix+tzdata, 나머지 플랫폼은 pix만 허용한다. Windows tzdata의 안정 버전은 `YYYY.N >= 2024.1`로 확인하며 다른 버전 문법은 명시적 검토 전 거부한다. helper hash와 active/inactive 요구를 실행 evidence에 남긴다.

## 실제 실행 결과

| 환경 / 명령 | 결과 |
| --- | --- |
| Linux Python 3.12.14, `python -m pytest tests/test_wheel_environment.py -q` | 26 passed |
| 변경 Python 4개 `ruff check` / `ruff format --check` | 통과. 첫 format 검사에서 새 helper 1줄 wrap 필요 → 해당 파일만 format 후 통과 |
| 외부 cwd, wheel Python `-I tools/check_mining_wheel.py --wheel WHEEL --site-packages SITE --source-root ROOT --output OUT` | success=true; source/wheel/install 249개 파일 bytes 일치 |
| 같은 격리 환경, `check_visualization_wheel.py` | success=true; JSON roundtrip·HTML payload·assets/provenance/license 확인. 실제 browser 실행 아님 |
| 같은 격리 환경, `check_native_wheel.py --wheel WHEEL --output OUT` | status=passed; source/wheel/install 249개 파일 bytes 일치 |
| Linux Python 3.10.21 설치·`uv sync --locked --extra dev --extra imports --python PATH --no-python-downloads` | 성공. 별도 환경, lock 변경 없음 |
| Python 3.10.21, `python -m pytest tests -q -rs --junitxml=OUT` | **6 failed, 10,544 passed, 40 skipped, 1,169 subtests passed / 211.12초** |
| Node Playwright 1.62.1 Chromium install | 실패. 받은 ZIP의 central directory 오류, 자동 재시도 후 directory lock stale 오류. 실제 browser 미실행 |

wheel은 앞선 동일 제품 코드로 만든 `pix-0.5.0-py3-none-any.whl`, SHA-256 `92a5d364760b0e267fd72fe9555404382bc61411faf7cf2f90b115ba1d8ba7dd`를 재사용했다. wheel site에는 pix 0.5.0만 설치되어 있다. tools-only 변경이므로 다시 build하지 않았으며 세 검사에서 현재 source와 실제 installed bytes를 대조했다. 이전 checker 실패를 소급해 통과로 바꾸지 않는다.

`26 passed` 중 linux/darwin/win32는 명시적 platform 인자를 사용하는 **단위 테스트**다. Windows/macOS 실제 실행이 아니다. 검증 범위에 추가 runtime 패키지를 설치해 오염된 환경을 정상으로 처리하지 않는다.

## Python 3.10에서 새로 드러난 구체 실패

| 파일·테스트 | 관측 | 분리 후속 |
| --- | --- | --- |
| `tests/case_centric/test_statistics.py::test_numeric_cancellation_preserves_small_centers` 3개 parameter | `statistics.pstdev`가 큰 제곱 variance를 float로 변환하며 OverflowError | 숫자 의미를 유지한 최소 버전 호환 수정 |
| `tests/event_log/test_xes.py::test_recursive_typed_attributes_no_flattening` | `.123456000` 소수초가 schema_invalid | 허용된 zero-tail 정밀도 보존 |
| `tests/ocel/test_compact_import.py::test_inferred_timestamp_attribute_precision_is_not_silently_truncated` | sub-microsecond 문자열이 timestamp로 인식되지 않아 precision 거부 누락 | inference와 precision 검사 일관성 |
| `tests/viewer/test_visual_contracts.py::test_time_chart_rfc3339_strings_retain_original_offset_and_precision`의 `.1Z` | 유효한 한 자리 소수초를 거부 | RFC3339 검사 계약 유지 |

제품 호환 수정은 이 tools-only 브랜치에 섞지 않고 별도 작업으로 분리한다. 기대값·skip을 변경하거나 Python 하한을 올려 통과시키지 않는다.

40 skip은 browser opt-in 27, Python Playwright 미설치 1, 외부 XES corpus 11, Windows reparse-point 전용 1이다. macOS/Windows 실제 실행, Python 3.13 독립 실행, 외부 corpus, browser, CI workflow는 이번 실행에서 미완료다. 이 보고서의 Python 3.10 실패는 후속 수정 전 스냅샷이며 후속 검증이 대체하더라도 최초 실패 기록을 유지한다.

같은 source/metadata/helper/환경에 한해 위 증거가 유효하다. 허용 dependency·marker·wheel bytes 변경, 새 설치 오염 반례가 있으면 해당 검사를 다시 연다. 현재 checker 버그 수정의 종료 기준은 충족했지만 전체 NEXT-04 지원 matrix 완료나 출시 승인으로 해석하지 않는다.
