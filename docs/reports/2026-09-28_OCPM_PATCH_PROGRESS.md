# OCPM 패치 진행·검증 기록

실행일: 2026-09-28. Base `2b515bcaa674f90cddf438fdfa4f6916e03e3d47`. 현재 작업은 미커밋이며 코드 diff는 `viewer/visualization.py::_source_metadata`의 16줄 추가다. 새 문서·테스트는 아래 목록으로 식별한다. 보고서 자신을 포함하는 diff hash는 만들지 않는다.

## 진행 범위

- OC-PATCH-01: [소비 계약·지원표](../specifications/PIX_OCPM_CONSUMPTION_CONTRACT.md) 1차 작성. 원문 P0/P1별 기존 근거와 미확인 항목을 분리했다. 전체 속성 사용 inventory는 미완료다.
- OC-PATCH-02: [도메인 사례](../user-guide/OCPM_DOMAIN_REVIEW_CASES.md) 작성. 손계산 count와 동일 숫자의 서로 다른 replay operator를 검증했다. 명시적 cardinality 제약을 위반하는 shared event 해석은 사용자 질문 응답 대기이며 도메인 승인으로 표시하지 않았다.
- OC-PATCH-03 일부: 계산 issue의 code/message/at를 각 입력 provenance의 `issues_json`에 보존. 여러 입력 또는 payload 없는 실패에서도 해당 계산과 위치가 유지된다. 문서 공통 issue 문자열은 그대로 유지한다.
- 04…10 전체 완료는 아니다. projection 소비 경로·OCPN 상시 표시·실제 browser·export 수락, 한도 실험과 조건부 P1 조사는 남아 있다.

## 실제 변경과 호환성

`VisualField`를 재사용했다. 새 runtime schema, 계산 status, result/model codec, canonical V1 또는 projection v2 변경은 없다. 기존 저장 visualization은 이 선택 detail이 없어도 읽을 수 있다. 새로 생성하는 visualization JSON은 detail 추가 때문에 bytes가 달라진다. 계산 source digest/computation identity가 달라진다는 뜻은 아니다.

`tests/viewer/test_ocpm_domain_review.py`에 다음 3개 테스트를 추가했다.

1. `test_hand_count_survives_visual_serialization_with_multiple_qualifiers`: 손계산 2 event pairs / 2 objects / 3 occurrences가 qualifier 중복 및 viewer 저장/복원 후 유지.
2. `test_equal_perfect_replay_values_remain_distinct_operators`: 명시적 한 객체 모델에 독립 사건 둘이면 두 replay의 fitness=1이며 operator·panel provenance는 분리.
3. `test_failed_inputs_keep_separate_issue_locations_without_panels`: 다른 실패 원인·위치가 input별로 JSON 저장/복원됨. synthetic immutable request/envelope로 실패 전달 계약을 검증하며 실제 search algorithm 검증은 아님.

## 실행 근거

Windows 11 x64, Python 3.13.15. 허용된 runtime:
`.artifacts/2026-09-13-validation-xes-corpus/runtime/python-3.13.15-embed-amd64/python.exe`.
pytest dependency 경로는 `.artifacts/2026-09-18-validation-residual-core/dependencies`를 `sys.path` 앞에 추가했다. 기존 runtime의 source/dependency 경로를 사용한 source-tree 검증이며 격리 wheel 검증이 아니다. 보안 설정이나 가상환경 실행 정책을 변경하지 않았다.

| 검사 | 실제 결과 |
| --- | --- |
| 신규 테스트 첫 작성 | fixture의 `spec=None`이 기존 immutable dataclass 계약을 위반: 1 failed / 226 passed. fixture를 기존 `OCDFGSpec`으로 수정. 제품 결함으로 집계하지 않음 |
| 이전 HEAD의 `_source_metadata`를 메모리에 로드한 반례 | `test_failed_inputs_keep_separate_issue_locations_without_panels`: 1 failed, 0.16초, `KeyError: issues_json`. working tree rollback 없음 |
| 집중 회귀 | 227 passed, 13 subtests, 0.71초 |
| viewer·OCPN·variant·n-gram·근사·projection·codec 통합 | 1,116 passed, 5.59초 |
| Ruff | 변경 Python 2개 check 통과. 새 테스트에만 format 적용 후 format check: 2 files already formatted |
| 전체 tests | **10,520 passed, 39 skipped, 1,169 subtests, 66.43초** |

39 skip은 opt-in browser 26, 외부 XES corpus 11, Python Playwright의 `greenlet._greenlet` 미설치 1, Windows symlink 생성 권한 1이다. 이 경로가 통과했다고 주장하지 않는다. 신규 테스트 3개만 추가되었으며 기존 skip 설정은 변경하지 않았다.

집중 실행 대상: `tests/viewer/test_ocpm_domain_review.py`, `tests/viewer/test_visualization.py`, `tests/viewer/test_visual_contracts.py`, `tests/compute/test_ocdfg.py`, `tests/object_centric/test_conformance.py`.

통합 실행 대상: `tests/viewer`, `tests/compute/test_ocpn_discovery.py`, `tests/compute/test_variants.py`, `tests/case_centric/test_context_ngrams.py`, `tests/case_centric/test_conformance_approximation.py`, `tests/object_centric/test_case_projection.py`, `tests/test_review_boundaries.py`, `tests/test_results.py`, `tests/test_extended_results.py`.

실행 형식은 다음과 같다. `<대상 목록>`은 위 집중/통합 목록을 순서대로 넣고 `-q`를 붙였다. 전체는 `['tests','-q','-rs']`다.

```powershell
& .artifacts/2026-09-13-validation-xes-corpus/runtime/python-3.13.15-embed-amd64/python.exe -c "import sys; sys.path.insert(0,'.artifacts/2026-09-18-validation-residual-core/dependencies'); import pytest; raise SystemExit(pytest.main([<대상 목록>, '-q']))"
```

Baseline 반례는 `git show HEAD:src/pix/viewer/visualization.py`의 bytes를 읽어 별도 Python 프로세스의 해당 module namespace에 `exec`한 뒤 신규 테스트 하나를 실행했다. 전체 baseline 패키지를 별도 설치·검증한 것은 아니다.

## 남은 판단·검증과 철회 조건

사용자 도메인 질문은 사례 2의 명시 모델 제약 해석이다. 다른 해석이면 profile/표시 사례를 분리하며, 기존 구현 변경을 승인받았다고 가정하지 않는다. 최신 OCEL 표준, Python 3.10/다른 OS, 깨끗한 wheel, 실브라우저 및 생산 규모 실험은 이번 묶음에서 아직 검증하지 않았다.

기준 code/profile이 바뀌거나 독립 반례가 발견되면 해당 소비 계약·직렬화·화면을 재검증한다. 이 결과는 기능 대체율·운영 준비 완료의 근거가 아니다. 공수·실무 성공률은 알 수 없음이다.

## 후속 묶음 — projection 연결·패널별 설명 (2026-09-28)

위 16줄 diff·10,520 통과는 첫 묶음의 실행 snapshot이다. 다음 변경을 포함하는 최신 diff/검증으로 혼동하지 않는다.

- `build_visualization(..., projection=...)` 선택 인자: 단일 CaseLog/결과와 파생 digest를 대조하고 source/spec 재투영으로 receipt의 대응을 검사한다. 원본·derived digest·객체형·tie·shared-event case 집합을 기존 provenance details에 보존한다. 새 codec 또는 projection profile은 만들지 않았다.
- 잘못된 digest, 원본 대응 변조, 다중 입력에 하나의 receipt 적용, 잘못된 타입을 거부한다. 기존 receipt 없는 API는 유지한다. 문서 합성 후 panel attribution도 유지한다.
- JS/CSS: 현재 panel의 계산 상태·operator·진단·투영 설명을 표시하고 SVG footer에 포함한다. 다른 panel로 이동하면 해당되지 않는 설명을 제거한다. raw 모델에 discovery 관측성 진단을 임의로 붙이지 않는다. 전체 Gesso 배지·UI 요구 완료는 아니다.
- `examples/ocpm_projection_review.py`: 손계산 사례를 native OCDFG 및 투영 Case DFG로 계산해 HTML/JSON 출력. 실제 Chromium으로 projected panel을 열고 receipt 문구를 확인, screenshot을 육안 확인했다. artifact는 `.artifacts/2026-09-28-ocpm-contracts/projection-example/`에 보존한다.
- browser runner의 `PIX_BROWSER_ARTIFACTS` 선택 환경변수로 이번 출력 위치를 지정했다. 기존 역사 browser artifact를 덮어쓰지 않는다. 기본 runner 경로/skip 정책은 유지했다.

### 후속 실행

| 검사 | 결과 |
| --- | --- |
| viewer/projection/boundary 집중 | 726 passed, 3.17초 (native case-result 추가 테스트 전 snapshot) |
| Node DOM UI | `node --test tests/viewer/test_visualization_ui.cjs`: 44 passed, 0 failed |
| Chromium opt-in | 13 passed, 9.08초. `PIX_RUN_BROWSER=1`, `PIX_BROWSER_ARTIFACTS=.artifacts/2026-09-28-ocpm-contracts/browser`, 대상 `tests/browser/test_visualization_browser.py` |
| 합성 예제 | 허용 Python으로 `examples/ocpm_projection_review.py --output .artifacts/2026-09-28-ocpm-contracts/projection-example` 성공; 별도 Node Playwright로 실제 projected panel 확인 |
| 최신 전체 tests | **10,523 passed, 40 skipped, 1,169 subtests, 48.87초** |

이번 40 skip은 opt-in browser 27(신규 interpretation 시나리오 1개 포함), corpus 11, Python Playwright greenlet 1, Windows symlink 1이다. 이 중 native visualization browser 13개는 위 별도 opt-in 실행에서 실제 통과했다. 나머지 browser/corpus를 이번에 실행했다고 주장하지 않는다. 변경 Python 4개 Ruff check/format 통과, `git diff --check` 통과. CSS 추가 마지막 줄의 CRLF가 공백 검사에서 잡혀 해당 줄만 LF로 정리했다; 계산·스타일 규칙 변경은 없다.

예제 screenshot smoke의 첫 inline `node -e` 명령은 PowerShell 인자 quoting으로 구문 오류가 났다. 제품 실행 전 실패이며, artifact 내 `.cjs` 파일로 같은 검증을 실행하여 통과했다. 기대값 변경이나 제품 회피 처리는 없었다.

미완료: 새 선택 경로의 규모별 비용, 깨끗한 wheel 검증, 환경별 matrix, 전체 P1 공백과 화면 카피·접근성 수락. 사용자 도메인 질문은 대기 상태를 유지한다. 이번 변경 역시 commit/push하지 않았다.

## 사용자 판단 반영 — 공동 참여 제약 (2026-09-28 후속)

앞 절의 질문 대기 기록은 아래 응답 이전 snapshot이다. 사용자는 명시 모델의 참여 제약을 위반하는 사건은 **현재 모델에 부적합**하며, 이를 허용할 **별도 프로세스 모델**이 필요하다고 판단했다. 부적합 판정 자체를 소비자 정책으로 넘긴다는 설명을 철회한다.

최종 대화 반영 정정 (2026-10-04): 중간 표현인 '한 번에 작업 하나'를 일반 동시 실행 제한으로 해석하지 않는다. 이번 반례는 **non-variable arc에 연결된 동일 객체형에서 binding 하나가 객체 둘을 요구하는 경우**다. variable arc 전체·다른 객체형의 동시 참여·활동 AND/XOR에 확대하지 않는다. PIX variable arc의 명시적 min/max는 확장 profile 조건이다. 이 정정은 문서의 의미 범위를 바로잡으며 계산 수식을 바꾸지 않는다.

기존 계산은 이미 `computed`와 `fitting=False`, `inadmissible_event_participation`을 구별한다. 계산 오류로 예외를 던져 근거를 잃는 대신, 정상 완료된 부적합 ObjectReplay에 viewer `conformance_verdict=not_fitting`과 명시적 위반 안내를 추가했다. 계산 미완료에는 이 완료 판정을 부여하지 않는다. flattened fitness=1로 덮어쓰지 않고 서로 다른 panel에 보존한다. 별도 모델을 자동 발견·대체하는 동작은 추가하지 않았다.

검증: `tests/viewer tests/object_centric/test_conformance.py -q` **740 passed, 13 subtests, 3.15초**; Node UI **44 passed**. 신규 반례는 한 객체 fixed arc에 두 객체가 참여하는 사건으로 joint 부적합·log deviation 1·flattened fitness 1·viewer 저장/복원 및 귀속을 확인한다. 이전 전체 suite/Chromium 수치는 이 마지막 표시 변경 이전 결과다. 변경 Python Ruff check 통과; 테스트 formatting 정리. commit/push 없음.

## 기준점 확정 전 재검증 (2026-10-04)

사용자가 미커밋 작업의 commit과 후속 작업 기준화를 요청했다. 작업 전 HEAD와 fetch한 원격 개발 브랜치는 모두 `2b515bcaa674f90cddf438fdfa4f6916e03e3d47`였다. 이번 재검증에는 위 마지막 부적합 표시 변경까지 포함한다. 제품 코드 의미 변경은 추가하지 않았고, non-variable arc 해석과 계획 문서의 역사 상태를 정정했다. 기준 commit SHA는 후속 인계 문서에서 식별한다.

| 실제 실행 | 2026-10-04 결과 |
| --- | --- |
| 전체 `pytest tests -q -rs` | **10,524 passed, 40 skipped, 1,169 subtests passed, 58.97초** |
| `node --test tests/viewer/test_visualization_ui.cjs` | **44 passed, 0 failed, 0 skipped**, 203.52 ms |
| `PIX_RUN_BROWSER=1`로 `pytest tests/browser/test_visualization_browser.py -q -rs` | **13 passed, 9.59초** |
| Python 변경 4개 Ruff check | 통과 |
| 같은 4개 Ruff format --check | 4 files already formatted |
| `examples/ocpm_projection_review.py --output .artifacts/2026-10-04-ocpm-baseline/projection-example` | 종료 0, HTML/JSON 생성 |
| `git diff --check` | 통과 |

Python 실행기는 앞 절과 동일한 승인된 embedded runtime이며, pytest는 앞 절의 dependency 경로를 추가한 `pytest.main(['tests','-q','-rs'])`로 실행했다. 브라우저도 동일 방식으로 대상만 바꿨다. `PIX_BROWSER_ARTIFACTS`는 이번 날짜의 artifact 하위 `browser`를 지정했다. Ruff는 같은 Python의 `-m ruff check`와 `-m ruff format --check`이며 대상은 `src/pix/viewer/visualization.py`, `tests/browser/test_visualization_browser.py`, `tests/viewer/test_ocpm_domain_review.py`, `examples/ocpm_projection_review.py`다.

실제 환경: Windows 11 build 26200, Python 3.13.15 AMD64, pytest 9.1.1, Ruff 0.16.6, tzdata 2026.4, openpyxl 3.1.5, pyarrow 25.0.1, Node v24.18.0. lock 동기화 또는 깨끗한 설치를 이번에 수행했다는 뜻은 아니다. Python 3.10, Linux/macOS, wheel 설치 격리 검증, 다른 browser suite, 외부 corpus와 생산 규모 비용은 이번에도 미실행이다.

전체 실행의 40 skip: opt-in browser 27, 외부 corpus 11, Python Playwright의 `greenlet._greenlet` 로드 실패 1, Windows symlink 권한 1. native visualization browser 13개만 별도 opt-in 실행으로 통과했다. 이 실행에서는 테스트 실패·재시도가 없었으며 skip을 통과에 합산하지 않는다. 전체 통과 수가 과거보다 하나 늘어난 것은 마지막 단계에 추가된 shared-participation viewer 반례를 포함하기 때문이다.

상세 로그: 로컬 ignored `.artifacts/2026-10-04-ocpm-baseline/{pytest-full.log,node-ui.log,browser.log}`. 이 로그·가상환경·사용자 첨부 `docs/PIX_review_5ef88a2.zip`은 commit 대상에서 제외한다. 원격 소비자는 이 표를 기존 실행 기록으로 읽고 자신의 실제 실행을 별도로 보고해야 한다.
