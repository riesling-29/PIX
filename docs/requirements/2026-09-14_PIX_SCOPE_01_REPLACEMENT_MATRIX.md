# PIX SCOPE-01 — PM4Py·OCPA 대체표

작성 기준일: **2026-09-14**. 대상 PIX는 현재 작업 트리의 **0.5.0**이다.
이 문서는 [사용자 요구사항](2026-09-13_PIX_SCHUMPETER_USER_REQUIREMENTS.md)과
[개발 플랜 SCOPE-01](2026-09-13_PIX_DETAILED_DEVELOPMENT_PLAN.md)의 공개 계산·variant 대조 목록이다.
기존 15개 기능군 gap 표를 **업무 질문 → 입력·출력 → 참조 계산 → 현재 PIX → 남은 작업**으로 세분화했다.

PM4Py·OCPA 계산을 PIX 자체 엔진으로 대체한다는 요구를 유지한다. 참조 라이브러리를 호출하는
wrapper를 개발 완료로 세지 않는다. Schumpeter의 Agent 실행·Skill·Hub는 별도 제품 책임이다.
이번 작업은 대체 목록과 근거 작성이며, 계산 엔진을 추가 구현한 작업은 아니다.

## 1. 읽는 순서와 상세표

도메인 검토는 아래 부록의 **질문·입력·확인할 출력·남은 개발·의미 차이**를 읽으면 된다.
함수명과 소스 경로는 개발자가 그 판단을 실제 구현에 연결하기 위한 추적 정보다.

| 부록 | 확인할 내용 |
|---|---|
| [PM4Py 발견·적합성·모델](scope-01/PM4PY_CORE.md) | Miner별 모델, alignment의 목적·변형, replay·평가 지표, 모델 의미·변환·축약 |
| [PM4Py 데이터·OCEL·입출력](scope-01/PM4PY_DATA.md) | 통계·필터·전처리, OCDFG·ET-OT·OTG, 객체 관계·feature, reader·writer |
| [PM4Py 고급 분석·운영·표시](scope-01/PM4PY_ADVANCED.md) | Encoding·예측 입력·조직·simulation·streaming, privacy, 설명·연결·시각화 |
| [OCPA 전체 대체표](scope-01/OCPA.md) | Execution·variant, OCPN·joint alignment·context, 성능·규칙·feature, AOPM |
| [공통 편의 기능](scope-01/SUPPORT.md) | 열 매핑·classifier·정렬·표본·문자열 입력·직렬화 wrapper |

총 **334개 검토 항목**이다. 아래 수는 행의 분류이며 알고리즘 수나 제품 완성률이 아니다.

| 부록 | 검토 항목 | 구현 있음 | 부분 대응 | 대응 구현 없음 |
|---|---:|---:|---:|---:|
| PM4Py 발견·적합성·모델 | 80 | 1 | 16 | 63 |
| PM4Py 데이터·OCEL·입출력 | 94 | 9 | 18 | 67 |
| PM4Py 고급 분석·운영·표시 | 79 | 0 | 4 | 75 |
| OCPA | 70 | 9 | 21 | 40 |
| 공통 편의 기능 | 11 | 0 | 5 | 6 |
| 합계 | **334** | **19** | **64** | **251** |

기계적으로 추적할 자료는 [대체 레지스트리](scope-01/replacement_registry.json),
[원천 식별자·파일 hash 목록](scope-01/reference_catalog.json),
[기존 참조와의 파일별 차이](scope-01/baseline_diff.json),
[정적 검증 결과](scope-01/validation.json)다. JSON을 읽어야 도메인 판단을 할 수 있는 구조는 아니다.

## 2. 상태를 해석하는 기준

**구현과 의미 대응은 서로 다른 축이다.** 모든 행은 아직 참조 대체 승인 전이다.

| 구현 상태 | 의미 |
|---|---|
| 구현 있음 | 해당 질문에 답하는 PIX 구현이 존재한다. 옵션 전체·참조와의 동치·대체 승인까지 뜻하지 않는다. |
| 부분 대응 | 기능의 일부만 있거나, 관련 primitive·별도 profile만 있다. 남은 기능과 의미 차이를 함께 기록한다. |
| 대응 구현 없음 | 해당 기능의 제품 계산 경로가 없다. 향후 출력 계약은 현재 지원이 아니다. |

| 의미 대응 | 의미 |
|---|---|
| 명시한 좁은 범위 대응 | 읽은 정의가 지원 범위에서 대응한다. 전체 입력에 대한 동일 실행 결과를 입증한 상태는 아니다. |
| PIX 자체 정의 | 같은 문제를 다루지만 PIX가 별도 profile·경계·분모·탐색 계약을 갖는다. 참조 정의 지원을 자동 대체하지 않는다. |
| 일부 의미 겹침 | 일부 집계·관측량·변환만 겹친다. 이름이 같아도 동일 지표로 취급하지 않는다. |
| 의미 대응 미검증 | 구현 존재와 별개로 참조 정의와의 대응 검증이 남았다. |
| 미구현 | 의미 대응을 판정할 PIX 계산이 아직 없다. |

부록의 **입력·출력은 대체할 기능의 검토 계약**이다. 참조의 정확한 Python 반환 타입이나
현재 PIX의 지원 보장은 아니다. 예를 들어 미구현 simulation의 완료·부분·한도 상태는 앞으로
PIX에서 구분할 출력이며, 현재 기능으로 표시하지 않는다. 정확한 단위·분모·동치·동률·결측 정책은
SCOPE-02에서 작은 정답 사례와 함께 확정한다.

표의 한 행은 검토 단위다. 하나의 계산을 감싼 여러 wrapper, deprecated alias, 저장 backend는
독립 알고리즘으로 세지 않는다. 반대로 같은 alignment 계열이어도 목적함수나 근사 방식이
다르면 별도 행 또는 변형으로 남긴다. **행 수와 79개 개발 작업 ID는 완성률·공수의 분모가 아니다.**

## 3. 고정한 참조와 조사 방법

공식 PyPI를 **2026-09-14 21:34 KST**에 조회하고 다음 wheel을 직접 다운로드하여 SHA-256을
재계산했다. 아래 판본은 조회 시점 최신 배포본이다. 참조 패키지는 설치·import·실행하지 않고
wheel의 Python 소스를 정적 분석했다.

| 항목 | PM4Py | OCPA |
|---|---|---|
| 고정 배포본 | [2.7.23.8](https://pypi.org/project/pm4py/2.7.23.8/) | [1.3.4](https://pypi.org/project/ocpa/1.3.4/) |
| wheel bytes | 2,666,577 | 213,756 |
| 분석한 Python 파일 | 1,658 | 203 |
| 이전 로컬 소스 | 2.7.23.3 / `3329bbcbadce8764f7df660fd88636c30793fbd0` | 1.3.3 / `de056e0203a3fa4a9bbc19a95e001eada323074a` |
| 이전 소스와 byte 동일 | 1,584 파일 | 198 파일 |
| AST 변경 | 73 파일 | 3 파일 |
| byte는 다르지만 AST 동일 | 0 | 1 파일 |
| 추가 파일 | 1 | 1 |

PM4Py wheel SHA-256:
`e97f7845bc440859fe46e88824bb773162d8799f1278b34907d0eb4c7d4be502`.
OCPA wheel SHA-256:
`52e8208d5ef8633060b905441498aa8b53e0322bf7a310c5a5deb49500da2934`.

AST는 docstring과 상수도 포함해 비교했다. 따라서 AST 변경 수는 알고리즘 변경 수가 아니며,
AST 동일성도 외부 의존성·옵션을 포함한 runtime 동등성을 입증하지 않는다.
이번에 확인한 기능 대부분을 “최신 판본에서 새로 추가된 기능”이라고 부르면 안 된다.
실제 추가 파일은 PM4Py의 `dijkstra_semantics.py`, OCPA의 `index_based_filtering.py`다.
나머지 파일별 차이는 원천 차이 목록을 따른다.

9월 12일 OCPA wheel 추가 비교가 완료되지 못한 기록은 당시 사실로 유지한다.
이번 다운로드·전체 Python 파일 대조는 별도의 새 증거이며 [참조 스냅샷](../reference-analysis/REFERENCE_SNAPSHOTS.md)에 추가했다.

## 4. 이번 대조에서 확인한 주요 범위

| 영역 | 현재 PIX에서 확인한 부분 | 대체표에 남긴 주요 개발·의미 검토 |
|---|---|---|
| I/O·로그 표현 | OCEL·XES·MXML·표 입력, CaseLog·OCEL 교환, OCEL 2 출력 | XES 등 writer, 모델 형식, legacy/enriched profile, 인메모리 표현·변환 차이 |
| 통계·필터 | DFG·OCDFG의 기초 집계와 명시한 분석 범위 | 일반 통계·필터·표본·기간·수명주기 전처리, 객체 관계를 보존한 결과 |
| 실행·variant | Connected/leading 실행, PIX incidence 동치 variant | 경계·overlap·동률, OCPA two-phase 동치와 차이, graph 변환 |
| 발견 | PIX IM profile·tree→PN·관측 cardinality OCPN | IMf·IMd, Alpha·Heuristics·ILP·POWL·Split·LPM·DECLARE 등 |
| Case 적합성·평가 | Bounded shortest alignment·결정적 replay·prefix precision | A*·근사·tree/DFG/edit-distance alignment, 정규화 fitness·다른 precision·generalization |
| 객체 적합성 | PIX joint alignment·binding·context 지표 | OCPA 실제 alignment·replay·context 모집단과 대응, PM4Py OCEL graph comparison |
| 성능·관계·규칙 | 관측 간격·명시 시작 시각의 service, 5종 PIX 규칙 | Readiness/waiting/pooling/lagging, qualifier·as-of, constraint graph·Declare 등 |
| Feature·조직·simulation·streaming | 일부 선행 모델·발화 primitive | Feature/encoding·split·조직망·자원 지표·playout·온라인 계산의 제품 API |
| Action·영향 | 선행 로그·모델 계산 일부 | OCPA AOPM 후보·일정·구조/객체/성능 영향. Agent 실행은 Schumpeter 책임 |
| 그래프·설명·연결 | DFG/OCDFG·PN/OCPN의 PIX ELK/SVG viewer | 나머지 모델의 도메인 표시, 계산 설명 자료, 외부 connector·LLM 경계 |

추가로 드러난 중요한 세부사항은 다음과 같다.

- **OCPA에도 joint alignment 계산 경로가 존재한다.** 이를 누락하지 않고 PIX의 concrete binding과
  비용·상태·실행 경계를 비교하도록 기록했다. 발견된 OCPN의 관측 적합성이 일반 soundness를 뜻하지 않는다.
- **PM4Py의 trace encoding은 15개 variant**다. 모델 진단·빈도·텍스트 embedding을 구분했고,
  deprecated `log_to_features` 경로는 새 계산으로 중복 집계하지 않았다.
- **OCPA feature는 등록 기준 event 27종, execution 10종**이다. 미래 정보가 포함된 feature와
  관측 시점 입력을 분리하고, 공유 객체·이벤트 때문에 발생하는 train/test 정보 누출도 검토 대상으로 남겼다.
- **PM4Py도 Graphviz만 사용하지 않는다.** OCDFG의 ELKJS, BPMN의 DAGREJS/BPMNIO 자동 배치,
  SNA의 PYVIS 경로가 있다. PIX의 선택은 backend 이름보다 모델 의미·근거·상호작용의 일관성으로 평가한다.
- **OCCN↔OCPN 변환은 이름만 보고 무손실로 취급할 수 없다.** Cardinality 완화·marking 생성·marker
  정보 손실을 각각 기록했다. Trace별 tree 축약도 전체 언어 보존 축약과 구분한다.
- **AOPM 일정 생성은 전역 최적 경로 보장의 근거가 아니다.** 참조의 후보·greedy 일정과 영향 계산을
  보존하면서 PIX가 어떤 목적·제약·종료 상태를 제공할지는 별도 정의한다.

각 주장의 정확한 경로와 변형은 위 세부표와 고정 wheel 식별자를 따른다. 참조 소스의 stub,
미등록 기능, dummy 반환, 잘못 연결된 인자·비교식은 부록 notes에 **정적 관찰**로 표시했다.
이번 작업에서 upstream 오류를 실행 재현한 것은 아니다. 잘못된 결과의 복제는 대체 수용 조건으로 채택하지 않았다.

## 5. 기존 플랜에 바로 연결되지 않는 경계

| 검토 ID | 발견한 기능 | 지금의 처리 | 후속 결정 |
|---|---|---|---|
| SCOPE-D01 | Trace variant privacy의 LAPLACE/SACOFA 및 contextual PRIPEL | 실제 계산군으로 보존. 기존 79개 작업에 직접 개발 작업이 없어 SCOPE-01에 연결 | 계산 요구의 누락인지 확인하고 독립 개발 항목·보장 조건·시험 방법 추가 |
| SCOPE-D02 | LLM용 분석 설명·검색·질의 생성과 외부 추론 호출 | 분석 자료 생성과 외부 서비스 orchestration을 각각 기록 | PIX의 계산/직렬화와 Schumpeter의 추론/실행 책임을 SCOPE-02/03에서 구분 |
| SCOPE-D03 | 9개 원천의 event-log/OCEL connector, OS 입력 수집 | 실제 공개 진입점을 누락 없이 기록. PIX core 구현 여부는 미확정 | 외부 adapter로 제공할 범위, 미지원 범위 또는 개발 보류를 명시적으로 결정 |
| SCOPE-D04 | Deprecated helper·메타데이터·CLI·backend 선택 | 기존 계산의 접근 경로로 추적 | 동일 Python API 복제가 필요한지와 native PIX 계약 제공을 구분 |
| SCOPE-D05 | PM4Py OCDFG·ET-OT·OTG의 graph comparison conformance | PM-OCEL-023/024에 보존. 기존 REL-03은 qualifier·시점 조건만 명시하므로 연결은 확장 제안 | REL-03 범위 확장 또는 별도 OCONF 개발 항목을 정하고 구조·빈도·fitness 정의 연결 |

계산군은 표에서 자동 제외하지 않았다. 반면 외부 애플리케이션의 모든 동작까지 이번 요청으로
PIX core에 구현하기로 확정한 것도 아니다. 미확정 항목은 결정을 남겨 두며, 독립적인 계산 개발은
진행할 수 있다. 비용 대비 필요가 없는 외부 연결은 **개발하지 않는 선택**도 범위 검토에서 가능하다.

## 6. 검증의 근거와 한계

이번 새 검증은 **원천 파일 hash·정적 식별자·대체표 연결·개발 작업 ID·문서 링크** 검증이다.
패키지 runtime 비교, 새 계산 구현, 전체 회귀 시험은 이번 SCOPE-01 작업에서 실행하지 않았다.
자세한 수와 종료 상태는 [정적 검증 기록](scope-01/validation.json)을 따른다.

| 정적 확인 대상 | 확인 결과 |
|---|---|
| PM4Py 최상위 모듈 공개 함수 정의 | 315개, 미연결 0 |
| `algorithm.py`·`factory.py`·`evaluator.py` 공개 함수 정의 | PM4Py 179개·OCPA 62개, 미연결 0 |
| 추출한 selector 등록 항목 | PM4Py 294개·OCPA 52개, 미연결 0 |
| 조건부 variant 추가 대입 | PM4Py 2개, 미연결 0 |
| 다운로드 소스 hash 재확인 | 1,861/1,861 파일 일치 |
| 기존 PIX 실행 증거와 현재 소스 연결 | 106/106 runtime 파일 hash 일치 |

여기서 공개 함수는 `_`로 시작하지 않는 정적 정의다. Selector는 `Variants`와 인식한
등록 dictionary를 추출하고 직접 분기·feature 등록을 수동 보완했다. **모든 내부 helper·임의의
runtime 동적 API를 전수 인증한 수치는 아니다.** 메타데이터·패키지 import alias는 별도 계산으로
계수하지 않는다. 공개 진입점과 selector에 연결한 helper도 독립 알고리즘으로 중복 계수하지 않는다.

재검사 도구는 [check_scope_registry.py](../../tools/check_scope_registry.py)다.
`python tools/check_scope_registry.py`로 레지스트리·문서·PIX 기준선을 검사한다.
공식 wheel을 위 SHA로 다시 확보한 경우 `--reference-root .artifacts/scope-01-2026-09-14`를
추가하면 소스 hash까지 대조한다. 일반 재검사는 기존 검증 기록을 덮어쓰지 않는다.

| 근거 ID | 이미 존재하는 실행 근거 | 사용할 수 있는 범위 |
|---|---|---|
| E-NATIVE | [v0.3 native 기록](../version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md) | Trace·DFG·execution·variant·시간·기본 실행 의미 등의 당시 시험 |
| E-MODEL | [v0.4 모델·평가 기록](../version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md) | IM·OCPN·joint alignment·context·precision·규칙 및 독립 oracle |
| E-IMPORT / E-OCEL | [v0.5 import 기록](../version/v0.5.0_IMPORT_IMPLEMENTATION.md) | 형식·손실·오류 검증과 실제 inventory OCEL 교환 |
| E-XES | [9월 13일 실제 XES](../version/v0.5.0_XES_CORPUS_2026-09-13.md) | 11 corpus+92 regression 통과. 대형 로그 모델 계산은 기록한 표본 범위 |
| E-VIEWER / E-INSTALL | [v0.5 통합·설치 기록](../version/v0.5.0_IMPORT_IMPLEMENTATION.md) | 기존 Chromium 13·JS 98, 설치 pipeline. 새 표의 미구현 기능 검증은 아님 |

현재 PIX runtime 소스 **106/106개 hash**가 기존 설치 wheel 검증 때의 기록과 일치한다.
이는 코드 기준선 연결의 증거이며, 기존 테스트에 없던 정의의 정확성을 새로 입증하지 않는다.
기존 전체 회귀 **4,184 passed·284 subtests·14 skipped**도 과거 실행 기록이다.
이번 표의 모든 행이 그 시험으로 검증됐다는 뜻은 아니다.

전체 대체율, 전체 알고리즘 수, 모든 입력에 대한 정확도, 성능 우위, 완성 소요 시간은 이 조사만으로는
**알 수 없음**이다. 함수·registry가 존재하는 것과 정상 실행·의미 동치·제품 대체 가능성은 구분한다.

## 7. 유효 범위와 다음 검토

이 판단은 위 wheel SHA와 현재 PIX 소스 기준선에 유효하다. 참조 배포본·대상 함수·PIX 구현·
의존성·표준 profile이 바뀌면 관련 행을 다시 점검한다. 아직 표에 연결되지 않은 공개 계산 경로가
발견되면 목록의 완전성 판단을 철회하고 추가한다. 같은 정의로 만든 독립 정답 사례에서 결과가
다르면 해당 행의 대응 판단을 철회하고 `의미 대응 미검증` 또는 `부분 대응`으로 낮춘다.

SCOPE-02에서는 우선 사용할 계산을 골라 **작은 입력 → 손으로 정한 기대 결과 → 경계·반례 →
PIX 결과와 근거** 순서로 검토한다. 채택한 예제는 회귀 테스트가 된다. 첫 묶음 후보는 실행 경계·
동시각 순서·빈도 분모이며, 회사 Agent 로그의 OCEL schema와 실제 fixture는 아직 확인하지 않았다.
그 호환성과 첫 검토 사례의 의미가 승인되었다고 간주하지 않는다.

**SCOPE-01의 산출물은 검토 가능한 대체 목록과 추적 근거다. 개별 계산의 의미 승인·대체 검증은
SCOPE-02 및 각 개발 작업에 남아 있다.**
