# PIX 잔여 개발: 입출력·계산 기반 구현 기록

작성: 2026-09-18. 대상: `feat/ocel-readers-v0.2.0` 작업 트리, 기준 HEAD `65cf9d557cfcbe1f8159b9a8600bb1aa60fe3fc9` 이후 변경.

## 범위와 책임

이번 변경은 [잔여 세부 설계](../requirements/2026-09-18_PIX_RESIDUAL_DETAILED_DESIGN.md)의 R01·R02·R03·R05·R06·R08 일부를 구현한다. **177개 잔여 항목 전체의 완료 보고가 아니다.** 기존 공동 체크리스트의 사용자 표시는 수정하지 않았고, 기존 완성률도 재산정하지 않았다. 현재 변경을 포함한 전체 기능 완성률은 재평가 전까지 **알 수 없음**이다.

수집은 Agent가 수행한다. PIX는 전달된 로컬 로그의 검증·변환·계산과 계산 결과의 직렬화를 수행한다. 추가한 CLI도 URL에서 데이터를 취득하지 않는다. 계산을 PM4Py/OCPA에 위임하지 않으며 기존 PIX 계산·계약을 재사용한다. ILP 공동 학습·설계 보류, 별도 미판정 항목과 Hub 자체 구현을 이번 변경으로 완료 처리하지 않는다.

## 구현과 추적

아래 상태는 **명시된 PIX profile의 구현과 테스트**를 뜻한다. 참조 라이브러리의 모든 옵션·문법과 동등하다는 표시는 아니다.

| 관련 ID | 추가한 동작 | 구현 및 검증 범위 |
| --- | --- | --- |
| PM-IO-002, PM-UTIL-011 | XES·gzip writer와 bytes 입출력 | 빈 trace, nested attribute, globals, classifiers, Unicode와 지원 metadata 왕복. 표현 불가 값은 저장 전에 거부. 원본 native ID는 출력 receipt로 대응 |
| PM-IO-011, PM-IO-014 | CSV/Parquet bundle writer | 관계 qualifier·속성 이력·미사용 schema 보존, 재수입 digest 확인 후 atomic publication. 실제 PyArrow 실행. compact CSV writer 확장은 이 변경의 범위가 아님 |
| OC-IO-005, PM-IO-013 | OCEL 1 JSON·gzip writer | classic profile. O2O·qualifier·이력 등 손실은 기본 거부. 명시 허용 시 손실 목록 반환. enriched/extended CSV/classic SQLite export 전체 완료는 아님 |
| PM-IO-017 | DFG 파일 reader/writer | 활동·시작/끝 빈도·edge 빈도. 교환 형식에 없는 case count·빈 trace 수 등은 생략 receipt로 표시 |
| PM-UTIL-009 | Process tree text parser | tau, quoted activity, sequence, XOR, parallel, binary loop. 임의 코드 실행 없이 문법·크기·깊이 검증 |
| PM-UTIL-010 | POWL text parser | 기존 POWL 계약을 재사용하는 PIX JSON text profile. upstream repr 문법 호환을 구현한 것은 아님 |
| PM-UTIL-006, PM-UTIL-008 | 속성 sequence 및 검산용 CaseLog 생성 | nested/typed 속성과 결측을 구별. JSON 활동 배열로 만든 합성 로그에는 실제 시각을 만들어 넣지 않음 |
| PM-EDGE-012, PM-UTIL-004 | 공개 CLI와 명시 열 mapping | inspect, dfg, ngrams, export-xes. CSV case/activity/time 열 선택. 원격 수집 없음 |
| OC-DATA-001, PM-OCEL-004 | 객체별 CaseLog 투영 | 객체 공유·복수 qualifier·속성 이력·원본 event ID의 대응 보존. 동시각 기본 거부, 명시 event_id 순서 허용. 전체 OCEL은 투영 receipt에 유지 |
| PM-ADV-007 | 문맥 n-gram | 활동과 선택 속성의 typed token, count/binary/TF-IDF, 학습 case 선택, 고정 vocabulary, 미등록 token 진단, 원본 event 증거와 자원 한도 |
| PM-DATA-004, PM-DATA-016, PM-DISC-025 | 경로 성능 계산 | 활동쌍 또는 variant 내 위치별 집계. 기본 complete→complete 간격, 별도 target 시각으로 의미 변경. 결측·음수·달력 범위 제외 이유와 occurrence 근거 |
| PM-DATA-019 및 업무시간 관련 항목 | 유한 업무 달력 | 주간 근무시간·휴일·IANA 시간대, DST 중복/존재하지 않는 시각 정책. UTC 구간 snapshot. KDE bandwidth 등 다른 잔여 범위는 미구현 |
| PM-DISC-014, PM-DISC-015 | POWL footprint, DFG 관계 | POWL의 기존 native PN 변환과 유한 탐색 재사용. DFG Alpha/Heuristics causal 관계·병행 관측·self-loop 분리 |
| PM-CONF-024 | 단일 trace 적합성 API | native 최소비용 alignment로 판단. 비용 0이면 적합, 탐색 한도이면 판단 불가. 빈 trace와 단일 case 조건 검증 |

## 도메인 관점에서 확인할 의미

**n-gram은 단어 빈도만이 아니다.** `검색 → 열기 → 검색 → 열기 → 저장`에서 `검색 → 열기`라는 2개 연속 행동은 두 번 발생한다. Count는 2, Binary는 1이다. `검색 → 열기 → 검색`은 3-gram이며 한 번 발생한다. 복합 속성을 지정하면 같은 활동도 도구·결과 등의 속성 값에 따라 다른 token으로 구별한다.

각 case는 별도 문서이고, 빈 case도 TF-IDF의 문서 수에 포함한다. 이 샘플의 TF-IDF는 `count × (log((1+문서 수)/(1+해당 묶음이 있는 문서 수))+1)`이며 L2 정규화를 사용하지 않는다. 높은 값은 성공률이나 최적 경로를 뜻하지 않는다. 학습에 선택하지 않은 case로 vocabulary와 IDF를 맞추지 않는다.

객체 A가 검색만 하고 객체 B가 저장만 했다면 객체별 분석에서 `검색 → 저장`은 0회다. 전체 시각순으로 잘못 합치면 1회가 생긴다. 샘플은 이 차이를 실제 계산 결과로 보여준다. 객체형 선택이나 동률 순서는 분석 가정이지 데이터로 증명된 인과관계가 아니다.

**성능 계산은 모집단을 분리한다.** `A → B → A → B`의 두 A→B를 합산하거나 variant 내 첫 번째·두 번째 위치로 구별할 수 있다. 간격을 자동으로 대기시간이라고 부르지 않는다. target start 시각을 제공하면 source complete→target start 간격을 계산할 수 있지만 lifecycle의 적절성은 입력 계약에 달려 있다. 근무시간 밖의 구간과 달력 자체가 정의되지 않은 구간도 구별한다.

**적합성과 미확정도 분리한다.** 단일 trace 판정은 log/model move 비용 1, sync/silent 비용 0인 기존 정확 alignment를 사용한다. 탐색 한도 중단은 부적합 판정이 아니다. POWL footprint도 bounded reachability의 완료 여부를 상속한다.

## 샘플과 재현

- [n-gram HTML](../../.artifacts/2026-09-18-validation-residual-core/ngram-review.html)
- [실제 렌더링 PNG](../../.artifacts/2026-09-18-validation-residual-core/ngram-review.png)
- [샘플 생성 코드](../../examples/residual_ngram_review.py)
- [공개 API와 CLI 사용법](../user-guide/RESIDUAL_CORE_GUIDE.md)

HTML과 JSON은 `.artifacts/2026-09-18-validation-residual-core/`에 있다. `.artifacts`는 로컬 검증 산출물이므로 Git으로 이동할 때는 생성 코드를 실행한다. 샘플은 합성 로그이며 실제 Agent 운영 성과를 주장하지 않는다.

```console
python examples/residual_ngram_review.py --output .artifacts/2026-09-18-validation-residual-core
```

출력 파일이 이미 있으면 writer의 기본 덮어쓰기 방지를 고려해 새 디렉터리를 지정한다. count/binary/tfidf 각각 27개 occurrence와 21개 feature column을 생성했다. 객체 경계 비교는 분리 0개, 잘못 합친 경우 1개 2-gram이다.

## 검증 기록

전체 `tests` 실행: **10,503 passed, 39 skipped, 1,169 subtests passed**, 50.45초. 근거: [JUnit XML](../../.artifacts/2026-09-18-validation-residual-core/pytest-final.xml). 테스트 수는 기능 수나 제품 품질 백분율이 아니다.

39개 skip은 브라우저 선택 실행 26개, 다운로드 XES corpus 선택 실행 11개, Python Playwright native greenlet 로딩 불가로 collection skip 1개, Windows symlink 권한 1개다. 이 회귀 실행에서 실제 다운로드 corpus와 전체 시각화 브라우저 테스트가 실행됐다고 주장하지 않는다.

추가한 테스트 파일은 `test_xes_export.py`, `test_cli.py`, `test_residual_ngram_example.py`, `event_log/test_utilities.py`, `model_io/test_dfg.py`, `model_io/test_text_models.py`, `ocel/test_bundle_export.py`, `ocel/test_legacy_export.py`, `object_centric/test_case_projection.py`, `case_centric/test_context_ngrams.py`, `case_centric/test_path_performance.py`, `case_centric/test_residual_relations.py`, `case_centric/test_trace_fit.py`다. 결과 직렬화 공통 검증에도 새 계산을 등록했다.

검증은 허용된 Python 3.13.15 runtime으로 수행했다. 기존 `.venv` 실행 정책은 변경하지 않았다. 그 환경과 ABI가 맞는 PyArrow 25.0.1 및 tzdata 2026.4를 별도 artifact dependency 경로에 설치해 Parquet와 DST 검증에 사용했다. Windows 시간대 지원을 위해 `pyproject.toml`에 조건부 tzdata dependency를 추가하고 `uv.lock`을 갱신했다.

n-gram HTML은 Node Playwright의 실제 Chromium으로 열어 page error 0, 가로 overflow 없음과 전체 screenshot을 확인했다. 이 검증은 n-gram 보고 화면에 한정된다.

변경·추가 Python 파일 37개의 Ruff 검사와 format 검사가 통과했고 `git diff --check`도 통과했다. 커밋·push는 수행하지 않았다.

## 아직 남은 범위와 판단 조건

R01에도 enriched OCEL 1 import, 추가 export profile, BPMN DI 및 추가 요소 교환 등 잔여가 있다. R02의 전체 필터·분포·lifecycle 확장, R04 모델 변환·축약, R05 나머지 discovery variant, R06 나머지 conformance 목적함수, R07 OC 계산, R08 나머지 학습, R09–R14의 채택 잔여 확장도 이 보고서로 완료 처리하지 않는다. 항목별 원래 범위는 [추적표](../requirements/2026-09-18_PIX_RESIDUAL_DESIGN_TRACEABILITY.md)를 유지한다.

위 지원 판단은 **2026-09-18의 이 작업 트리와 명시된 profile**에 유효하다. 손계산과 다른 집계, 보존한다고 한 데이터의 손실, case 경계를 넘는 n-gram, 검증 자료의 학습 유입, 중단된 탐색의 부적합 확정이 재현되면 해당 지원 판단을 철회하고 결함으로 처리한다. 코드·입력 profile·의존성 판본이 바뀌면 관련 검증을 다시 수행해야 한다. 참조 전체와의 동등성 및 남은 공수는 이 테스트 결과만으로 알 수 없다.
