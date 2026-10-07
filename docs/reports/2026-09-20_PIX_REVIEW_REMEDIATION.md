# PIX 5ef88a2 리뷰 재검증 및 보완

실행일: 2026-09-20. 브랜치 `feat/ocel-readers-v0.2.0`. 실제 시작 HEAD와 리뷰 기준은 모두 `5ef88a2184a639f279119c31d89c5071f87c8fa7`이다. 시작 시 미추적 파일은 사용자 첨부 `docs/PIX_review_5ef88a2.zip` 하나였으며 원본을 수정하지 않았다. 적용 가능한 별도 AGENTS.md는 상위 경로·저장소에서 발견되지 않았고 세션의 사용자 원칙을 적용했다. commit/push/병합/릴리스는 하지 않았다.

이 보고서의 현재 검토 기준은 위 base commit 대비 staged remediation 14개 파일과 아래에 구분한 실제 검증 실행 이력이다. staged 전체 diff나 이 보고서를 포함한 해시를 최종 canonical identifier로 사용하지 않는다. 이전 로컬 manifest는 당시 실행 스냅샷의 자료이며 현재 staging 상태의 식별자로 이월하지 않는다.

Staged 범위는 README, 이 보고서, `RESIDUAL_CORE_GUIDE.md`, `examples/review_consumer.py`, 소스 6개(`statistics.py`, `cli.py`, `case_projection.py`, `ocel/ingest/contract.py`, `ocel/model.py`, `visual_case_adapters.py`), 새 테스트 4개(`test_weighted_alignment_oracle.py`, `test_review_identity.py`, `test_review_boundaries.py`, `test_review_consumer.py`)다. 사용자 첨부 ZIP, `.artifacts`, 가상환경, 다운로드 로그는 포함하지 않는다.

## 판정과 변경

| 항목 | 최초 판정 → 처리 | 실제 근거·남은 범위 |
| --- | --- | --- |
| REV-01 | 재현됨 → 최소 의미 수정 | `Object.__post_init__`의 중복 키만 UTC instant로 비교. 저장한 datetime은 그대로. generic unique 함수 불변. 직접 fold, 동일 instant offset 중복, 다른 속성·마이크로초, UTC 범위 초과, JSON reader 검증 |
| REV-02 | 재현됨/계약 보완 → 정규화 | 원본 receipt를 분리하고 `project_object_cases`에서 기존 ComputationContext를 재사용. UTC 이력·속성 값·collection 정규화. 파생 metadata와 receipt에 projection v2 명시 |
| REV-03 | 설계·표시 보완 | UTC 가정이 숨겨졌다는 해석은 반증됨: 기존 reader 경고·transformation count·metadata가 존재. strict `require_ocel` admission과 CLI receipt 저장 보완. 결과 codec/status 변경 없음 |
| REV-04 | 기존 구현 확인 + 표시 보완 | temporal population·path count 불변식·결측/달력/음수·빈 모집단 기존 테스트 재사용. cycle 수식 유지, docstring·viewer 명칭 보완, 동일 10초 두 case 반례 추가 |
| REV-05 | 검증·연결 공백 보완 | Task/Agent component 및 leading overlap 반례. 기존 object_types boundary로 Task 범위 표현 가능하므로 추출 알고리즘 불변. 공유 원본 event audit와 기존 LeakageSplitSpec 그룹 연결 추가 |
| REV-06 | 검증 보완 | 기존 state-machine oracle의 한계를 명시하고 유한 weighted fork/join·다중 token·silent/duplicate label의 독립 언어/거리 oracle 추가. 기존 joint shared-event oracle 재실행. wheel 외부 설치·extra 진단 및 실제 실행 |
| REV-07 | 문서 보완 | README에서 과거 import 릴리스와 현재 XES writer 구분, 후속 요구/검토 안내. 역사 registry·평가·177개 사용자 표 불변. 이번 근거는 아래 ID별 후속 표에 한정 |
| REV-08 | 소비자 예제·테스트 | `review_consumer.py`는 기존 import/projection/temporal 계산과 JSON 결과를 조합. v1 성공과 v2 미확정 분리. 새 Hub/harness/범용 lineage engine 없음 |

## 수정 전과 후

첨부 README의 ‘미실행 제안 테스트’라는 설명을 그대로 출발점으로 삼았다. 네 기대값은 aware datetime 허용 계약, canonical 동치, 사용자가 채택한 파생 identity 요구와 일치했다.

수정 전 `.artifacts/2026-09-20-validation-review/test_review_regressions.py` 실행에서 다음 네 테스트가 모두 실패했다. `baseline.xml`에 남겼다.

- `test_distinct_fold_instants_are_not_duplicate_object_assignments`: Object 생성자에서 중복 오류.
- `test_canonical_equivalent_attribute_order_has_same_projected_identity`: 파생 digest 불일치.
- `test_canonical_equivalent_offset_has_same_projected_identity`: 파생 digest 불일치.
- `test_projected_object_history_is_ordered_by_absolute_time`: 이력 순서 역전.

동일 반례는 `tests/object_centric/test_review_identity.py`에 출처 설명과 함께 보존했다. 수정 후 해당 네 건·기존 projection·OCEL 테스트는 567 passed, 1 skipped, 46 subtests passed였다. skip은 Windows symlink 생성 권한이다. builder 뒤가 아니라 Object 생성 전에 실패한 경로를 직접 검증했다.

그 후 새 경계·소비자·weighted oracle 및 기존 classical/joint oracle·학습 cutoff·n-gram·path·temporal·CLI를 묶어 601 passed, 7 subtests passed를 확인했다. 중간 소비자 예제에서 format 인자 누락을 수정했고, 별도 wheel smoke 작성 중 기대 예외 타입과 receipt 필드명을 실제 계약에 맞게 수정했다. 이를 PIX 제품 결함 수정으로 집계하지 않는다.

## 정의 → 구현 → 검증 추적

| 요구 ID / 범위 | 정의·함수 | 반례/기존 테스트 및 한계 |
| --- | --- | --- |
| REV-01, canonical foundation | 객체 속성 assignment = 이름 + UTC instant; `Object.__post_init__` | `test_review_identity`, `test_review_boundaries::test_same_instant_duplicate_and_utc_range_are_not_repaired`, `test_reader_absolute_history_and_duplicate_rejection`; 범위 초과는 OverflowError이며 보정 없음 |
| OC-DATA-001, PM-OCEL-004 | `project_object_cases`, profile v2 | offset·fold·속성 순서·collection 재배열·datetime 값, 공유 event·qualifier·빈 객체·excluded event 기존 검증. raw receipt 전체의 동등성 요구는 아님 |
| PM-EDGE-012, PM-UTIL-011 / REV-03 | `ImportResult.require_ocel`, `ObjectCaseProjection.describe`, CLI `--receipt-output` | UTC assumption의 저장 가능성과 소비자 admission을 분리. import/result JSON의 저장 후 codec 복원. receipt와 원본을 따로 보관해야 함 |
| PM-DATA-004/016/038, PM-DISC-025 | `measure_path_performance`, `measure_case_performance` | 기존 모집단/한도/결측 테스트 + 동일 10초 두 case에서 cycle 5초, 평균 service 10초. 새 수식 없음 |
| PM-OCEL-013, PM-ADV-001/007 | `shared_event_case_groups`, `audit_projected_split`, 기존 `leakage_safe_split` | 공유 Agent만으로 누출 그룹 만들지 않음. 동일 원본 event를 공유한 두 case는 원자 그룹으로 재분할하거나 unavailable. 일반 통계 독립성 보증 아님 |
| PM-CONF-003/024 | `align_traces`, 기존 trace_fit | `test_weighted_alignment_oracle`: 독립 token 산술의 유한 accepting word 열거와 insertion/deletion DP. fork/join, weight 2, silent, duplicate label. oracle 한도 초과는 assertion 실패. 일반 무한 net 검증 아님 |
| OC-CONF-004 및 joint alignment 경계 | 기존 joint alignment oracle | `test_object_alignment_oracle`: 두 객체형 각 1개 token의 유한 product Bellman–Ford와 shared event 한번 소비. 모든 weighted OCPN의 증명은 아님 |
| REV-08, PM-EDGE-002 연동 경계 | `examples/review_consumer.py` | namespace/snapshot/version/hash·source digest·관측 cutoff/open 상태·import/projection·operator/result identity 제공. `test_review_consumer`에서 v2 수정 후 v1 성공을 v2에 전파하지 않음 |

학습 cutoff·held-out 변경에 대해서는 이미 `test_feature_dataset`의 미래 활동·잘못된 feature 값 불변, `test_context_ngrams`의 선택된 학습 case만 fit, `test_features`의 객체 `as_of` 이력·미래 join 차단이 있었다. 이 경로를 유지했다. 투영 receipt의 전체 객체 이력을 아무 feature에나 직접 넣어도 안전하다는 주장은 하지 않는다. online encoder는 시간 없는 trace/log 속성을 제거한다. 전체 원본 provenance digest는 미래 입력 변경에 따라 달라질 수 있다.

## identity 및 호환성

Canonical V1 바이트 정의와 golden 파일, 일반 CaseLog의 source-order digest는 변경하지 않았다. 원본 OCEL은 receipt.source에 유지하고 파생 표현만 정규화한다. projection v2 metadata가 들어가므로 기존 v1 파생 CaseLog digest와 downstream computation ID는 바뀐다. 이전 파생 캐시를 v2로 재사용하지 말고 재계산한다. persisted 기존 result codec은 유지하며 전역 operator version을 변경하지 않았다. projection receipt는 새 범용 result schema가 아니다.

computation ID는 요청 identity이지 진실성 서명이 아니다. strict admission은 알려진 timezone 가정을 거부할 뿐 수집 신뢰도 전체를 검증하지 않는다. CLI sidecar는 결과와 import/projection을 연결하지만 다중 파일 atomic transaction은 아니며 원본 데이터의 대체 저장도 아니다.

## 실행 환경과 검증

| 실행 구분 | 환경·결과 | 범위 |
| --- | --- | --- |
| 수정 전 첨부 반례 | Windows x64, Python 3.13.15; 4 failed, 0.18초 | 실제 기준 HEAD에서 실행. 독립 datetime 실험만의 결과가 아님 |
| 집중 A | 567 passed, 1 skipped, 46 subtests; 5.30초 | 첨부 4건, projection, OCEL reader/builder/canonical golden |
| 집중 B | 601 passed, 7 subtests; 1.91초 | 보완 경계와 기존 독립 oracle·cutoff·n-gram·path·temporal·CLI |
| 전체 `tests` | **10,517 passed, 39 skipped, 1,169 subtests**, **61.88초** | `full.xml`. 39 skip = opt-in browser 26, corpus 11, Python Playwright native dependency collection 1, Windows symlink 권한 1 |
| 실제 XES corpus 별도 | **11 passed, 183.89초** | `corpus.xml`; 실제 로그 원본 비교. mining은 테스트가 정의한 bounded whole-trace sample |
| Node Playwright / JS 별도 | 첫 실행 2 failed/10 passed; 재실행 **12 passed, 7.00초** | `browser.xml`, `browser-retry.xml`. 첫 실패는 Page.captureScreenshot 오류와 뒤따른 panel coverage 부족. 원인 미확정, 테스트·기대값·browser 코드를 수정하지 않고 재실행 성공 |
| 외부 wheel 환경 — staging 최소화 전 | Windows x64, 별도 Python 3.13.15; **14 passed, 1.40초** | 당시 빌드한 wheel만 설치한 저장소 밖 site에서 보완 테스트. 실제 CLI result+receipt 저장 성공. 이후 EOL/format 최소화한 현재 staged bytes로 재빌드한 결과는 아님 |
| 선택 의존성 | core만 설치 시 Parquet 요구 진단; PyArrow 25.0.1 설치 후 왕복 성공 | tzdata 2026.4의 Windows ZoneInfo 동작. 해당 wheel에서 경계 테스트 실행. 이후 staging 정리에서 bundle 구현 변경 없음 |
| 최소 Python/타 OS | Python 3.10, Linux, macOS **미실행** | 이번 runtime matrix의 공백. metadata의 `>=3.10` 선언을 실행 증거로 해석하지 않음 |
| 나머지 browser/extra 경로 | 별도 전체 browser suite와 모든 optional dependency 조합 **미실행** | Node 12개 시나리오 통과를 모든 브라우저·화면 검증으로 확대하지 않음 |
| 정적 검증 — staging 최소화 전 | 당시 변경/추가 Python 11개 Ruff check/format 및 working-tree `git diff --check` 통과 | 당시 파일 표현에 대한 기록. 신규 미추적 파일까지 staged 공백 검사가 완료됐다는 뜻은 아님. pytest 9.1.1, Ruff 0.16.6은 lock 판본과 일치 |
| staging 최소화 후 집중 회귀 | Windows x64, Python 3.13.15; **11 passed, 0.51초** | `test_review_identity.py`, `test_review_boundaries.py`. 코드·테스트의 정리 전후 AST 동일성도 확인 |
| 현재 staged model format | staged `ocel/model.py` 단독 Ruff format check **exit 1** | 기존 formatting과 변경 외 영역의 원래 EOL을 보존한 결과. 새 계산 결함이나 semantic failure가 아님. 최종 staged 전체 format 통과를 주장하지 않음 |
| staged 공백 검사 | `git diff --cached --check`: 출력 없음, **exit 0** | 테스트 LF 정리와 model 최소 diff 적용 후 확인. Ruff format 검사와 다른 검사 |

이전 sourceChangeId와 wheel 해시는 현재 staged 상태의 최종 식별자로 사용하지 않는다. 기존 `.artifacts/2026-09-20-validation-review/change-manifest.json`, `tracked-changes.patch`, wheel은 staging 최소화 전 검증 자료로 보존한다. 이 문서 수정에 따라 해시를 다시 계산·삽입하는 절차는 두지 않는다.

현재 staged `ocel/model.py`에는 전체 LF 정규화가 포함되지 않는다. 불필요한 EOL/format churn을 제거하고, 이름과 UTC instant로 객체 속성 중복을 판단하는 DST fold 수정만 남겼다(7행 추가·1행 삭제). 수정 구간 밖의 bytes는 HEAD와 동일하게 복원했다. `test_review_identity.py`는 CRLF를 LF로만 바꿨고 의미·assertion·테스트 데이터는 바꾸지 않았다. 이 두 파일은 정리 전후 AST가 동일하다. 이후 해당 두 테스트 파일의 11개 테스트를 재실행했으며 전체 suite와 wheel 검증을 다시 실행했다고 주장하지 않는다.

현재 상태에 직접 관련된 실제 실행 명령과 결과는 다음과 같다. 실행일은 2026-09-20이며 runtime 경로와 추가 dependency 경로는 아래 명령에 명시했다.

```powershell
& .artifacts/2026-09-13-validation-xes-corpus/runtime/python-3.13.15-embed-amd64/python.exe -c "import sys; sys.path.insert(0,'.artifacts/2026-09-18-validation-residual-core/dependencies'); import pytest; raise SystemExit(pytest.main(['tests/object_centric/test_review_identity.py','tests/test_review_boundaries.py','-q']))"
# 11 passed in 0.51s
```

staged model의 format 확인은 `git show :src/pix/ocel/model.py`의 bytes를 subprocess stdin으로 같은 runtime의 `-m ruff format --check --stdin-filename src/pix/ocel/model.py -`에 전달해 실행했으며 exit 1이었다. 이 결과를 통과로 바꾸기 위한 전체 파일 재포맷은 하지 않는다. `git diff --cached --check`는 별도로 실행해 exit 0을 확인했다.

wheel은 기존 .venv와 분리해 빌드하고 `%TEMP%/PIX-review-5ef88a2-20260920`의 새 공식 embedded Python runtime과 site 경로에 설치했다. smoke의 sys.path에는 repository/src, 기존 .venv, PYTHONPATH가 없음을 assertion으로 확인했다. Python 실행 정책·보안 설정은 변경하지 않았다. pyproject는 변경하지 않았으며 core Windows tzdata 및 선택 Parquet 의존성을 lock의 tzdata 2026.4, PyArrow 25.0.1과 대조했다. extras 미설치는 명시적 `ValueError: Parquet export requires pix[parquet]`, 설치 후 실제 canonical digest 왕복을 확인했다.

최소 지원 Python 3.10과 Linux/macOS는 이번에 실행하지 않았다. 설치 성공을 실행 검증으로 대체하지 않으며 해당 환경 지원을 새로 승인하지 않는다. 원래 full-suite skip과 명시적으로 별도 실행한 browser/corpus를 구별한다.

재현 명령(일반 구성 환경):

```console
python -m pytest tests/object_centric/test_review_identity.py tests/test_review_boundaries.py tests/test_review_consumer.py tests/compute/test_weighted_alignment_oracle.py -q
python -m pytest tests -q
python examples/review_consumer.py --output <새 디렉터리>
```

실제 실행은 허용된 `.artifacts/2026-09-13-validation-xes-corpus/runtime/python-3.13.15-embed-amd64/python.exe`와 PyArrow/tzdata가 있는 별도 dependency 경로를 사용했다. `PIX_RUN_BROWSER=1`, `PIX_RUN_XES_CORPUS=1`은 해당 별도 실행에만 설정했다. 세부 XML·로그·wheel·source 변경 manifest는 `.artifacts/2026-09-20-validation-review/`에 보관한다.

## 유지한 구현과 잔여 한계

`pix.api`의 native facade와 `engine.compute`의 명시 request dispatch는 실제 구현돼 있다. `intelligence/findings.py`는 미래 소유 위치이며 동작이 없다. 이를 채우려고 빈 프레임워크나 가짜 기능을 추가하지 않았다. 초기 v0.1의 비범위를 후속 discovery/conformance에 소급하지 않는다. PM4Py/OCPA runtime, 수집·인증·Hub 운영, Schumpeter 저장소 변경은 없다. ILP 및 미판정 선택은 유지한다.

역사 registry의 `native_profile`·partial·외부 runtime 미검증·대체 검증 구분을 승격하지 않았다. 이 표의 반례 보완은 upstream 전체 옵션 동등성이나 `reference_replacement_verified` 승인이 아니다. 전체 대체율·남은 공수·실무 성공률·메모리 및 처리량 성능은 알 수 없음이다. corpus·테스트 실행 시간도 제품 처리량 benchmark로 일반화하지 않는다.

복수 source snapshot 간 namespace 조정, version identity의 외부 진실성, 일반 weighted joint OCPN 증명, 운영 Hub 통합, 전체 optional 환경과 실데이터 도메인 인수는 남는다. 반복 event ID라도 namespace가 다르면 별도 원본일 수 있으며 단일 projection split 감사로 복수 snapshot 전체의 독립성을 선언할 수 없다.

**Non-blocking follow-up test:** strict timezone admission 거부와 `--receipt-output` 저장을 함께 사용하는 경로의 전용 테스트는 후속으로 추가한다. 현재 테스트는 성공 receipt 저장과 strict 거부를 각각 검사한다. 결합 경로의 테스트 공백을 이번 커밋의 blocking issue로 올리지 않으며 이번 문서 정리 단계에서 새 테스트는 추가하지 않는다.

판단 효력은 명시한 base commit 대비 staged remediation 범위와 입력·유한 profile, 위에서 구분한 실제 검증 실행에 한정한다. golden 변경, 원본 손실, shared-event split 누출, cutoff 이후 자료 유입, 중단 탐색의 false 확정, 모집단 불변식 위반이 재현되면 해당 지원 판단을 철회한다. 모델·입력 의미·dependency·projection profile 변경 시 영향 테스트와 wheel smoke를 재실행한다.
