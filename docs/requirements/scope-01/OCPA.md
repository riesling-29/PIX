# SCOPE-01 세부 대체표 — OCPA 전체 계산·입출력·시각화

기준일: **2026-09-14**. [전체 범례·증거·판정 경계](../2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md).
입력·출력은 대체할 기능을 검토하기 위한 계약이다. **현재 PIX가 이미 그 결과를 반환한다는 뜻은 아니다.** 현재 지원은 각 행의 구현·의미·소스·증거로 구분한다.
참조 경로와 symbol은 공식 배포 wheel의 위치다. wrapper·helper·backend는 추적을 위해 함께 표시하며 별도 계산 알고리즘으로 중복 집계하지 않는다.

| ID | 도메인에서 판단할 질문 | PIX 구현 | 의미 대응 | 다음 작업 |
|---|---|---|---|---|
| [OC-EXEC-001](#oc-exec-001) | 공유 객체로 연결된 이벤트를 하나의 실행으로 묶으면 어떤 실행과 미배정 이벤트가 생기는가? | 구현 있음 | PIX 자체 정의 | OCEXEC-01, OCEXEC-04 |
| [OC-EXEC-002](#oc-exec-002) | 지정한 leading 객체를 중심으로 어떤 객체·이벤트가 실행에 포함되고 실행끼리 얼마나 겹치는가? | 구현 있음 | PIX 자체 정의 | OCEXEC-01, OCEXEC-04 |
| [OC-EXEC-003](#oc-exec-003) | 객체의 이벤트 순서를 어떤 직접 후속 관계 graph로 표현하는가? | 부분 대응 | 일부 의미 겹침 | OCEXEC-02, OCEXEC-03 |
| [OC-EXEC-004](#oc-exec-004) | 두 실행의 활동·객체 참여 graph가 같은 variant인가? | 구현 있음 | PIX 자체 정의 | OCEXEC-03, OCEXEC-04 |
| [OC-EXEC-005](#oc-exec-005) | 전수 graph 동형 비교로 실행 variant를 분류할 수 있는가? | 부분 대응 | 일부 의미 겹침 | OCEXEC-03, OCEXEC-04 |
| [OC-DISC-001](#oc-disc-001) | 객체별 관측 흐름을 통합해 공동 참여와 variable arc를 가진 OCPN을 찾는가? | 구현 있음 | PIX 자체 정의 | DISC-01, DISC-02, OCONF-04 |
| [OC-DISC-002](#oc-disc-002) | 예전 OCPN 발견 경로의 Alpha·IM·DFG miner 선택은 어떤 통합 모델을 만드는가? | 부분 대응 | 일부 의미 겹침 | DISC-01, DISC-03, MODEL-04 |
| [OC-DISC-003](#oc-disc-003) | 발견한 OCPN에 성능 진단을 결합한 enhanced 모델을 얻는가? | 대응 구현 없음 | 미구현 | MODEL-06, PERF-03, VIEW-02 |
| [OC-CONF-001](#oc-conf-001) | 실행의 이벤트·객체 참여를 OCPN과 맞추는 최소 비용 joint alignment는 무엇인가? | 구현 있음 | PIX 자체 정의 | OCONF-01, OCONF-04 |
| [OC-CONF-002](#oc-conf-002) | 공동 객체 흐름의 missing/remaining/consumed/produced token과 fitness는 얼마인가? | 대응 구현 없음 | 미구현 | OCONF-02, OCONF-04 |
| [OC-CONF-003](#oc-conf-003) | 객체형별로 평탄화한 replay 점수를 합산하면 어떤 fitness가 나오는가? | 부분 대응 | 일부 의미 겹침 | OCONF-02, CONF-02, MODEL-06 |
| [OC-CONF-004](#oc-conf-004) | 객체별 과거 context에서 로그와 모델의 가능한 다음 활동이 얼마나 일치하는가? | 구현 있음 | PIX 자체 정의 | OCONF-03, OCONF-04 |
| [OC-CONF-005](#oc-conf-005) | Silent transition 경로와 token flooding을 replay에서 어떤 정책으로 다루는가? | 대응 구현 없음 | 미구현 | OCONF-02, QA-03 |
| [OC-PERF-001](#oc-perf-001) | 이벤트의 선행 입력 도착 차이로 flow·sojourn·synchronization·pooling·lagging·readiness를 계산하는가? | 대응 구현 없음 | 미구현 | PERF-01, PERF-02 |
| [OC-PERF-002](#oc-perf-002) | EOG에서 특정 활동의 elapsed/remaining 시간이 어떤 구간을 뜻하는가? | 부분 대응 | 일부 의미 겹침 | PERF-01, PERF-02, PERF-04 |
| [OC-PERF-003](#oc-perf-003) | 활동에 참여한 객체 수와 객체별 활동 발생 수의 분포는 얼마인가? | 부분 대응 | 일부 의미 겹침 | STAT-01, STAT-02, PERF-01 |
| [OC-PERF-004](#oc-perf-004) | Replay token 도착과 실제 시작·완료를 연결한 OPERA 성능은 얼마인가? | 부분 대응 | 일부 의미 겹침 | PERF-01, PERF-03, PERF-05 |
| [OC-PERF-005](#oc-perf-005) | 모델 activity·arc 빈도와 객체 참여/fitness 진단을 어떻게 집계·annotation하는가? | 대응 구현 없음 | 미구현 | PERF-03, MODEL-06, VIEW-02 |
| [OC-PERF-006](#oc-perf-006) | 성능 표본을 평균·중앙값·표준편차·합·최소·최대로 요약하면 어떤 값인가? | 대응 구현 없음 | 미구현 | PERF-01, STAT-03 |
| [OC-MODEL-001](#oc-model-001) | OCPN place·transition·arc·marking과 변경을 표현하고 저장할 수 있는가? | 구현 있음 | PIX 자체 정의 | MODEL-01, MODEL-03 |
| [OC-MODEL-002](#oc-model-002) | 객체형별로 특정 활동의 선행·후행 노드와 두 활동 사이 subnet을 구할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-05, MODEL-06 |
| [OC-MODEL-003](#oc-model-003) | 객체형·subprocess로 OCPN을 투영하거나 일부 활동을 숨길 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-06 |
| [OC-MODEL-004](#oc-model-004) | 보존 조건 아래 OCPN의 불필요한 place·transition을 줄일 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-06, QA-01 |
| [OC-MODEL-005](#oc-model-005) | 선택 활동과 객체형이 subprocess의 참여 조건을 만족하는가? | 대응 구현 없음 | 미구현 | MODEL-01, MODEL-05, MODEL-06 |
| [OC-FILTER-001](#oc-filter-001) | 빈도가 낮은 활동·variant나 선택하지 않은 실행을 제거할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, FILTER-03 |
| [OC-FILTER-002](#oc-filter-002) | 시간창에 시작·끝·포함·겹침 조건을 만족하는 실행 또는 이벤트만 선택하는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, FILTER-03 |
| [OC-FILTER-003](#oc-filter-003) | 활동·객체형 목록이나 빈도로 OCEL을 선택하는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, FILTER-03 |
| [OC-FILTER-004](#oc-filter-004) | 이벤트·객체 속성 조건을 만족하는 데이터만 남기는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, REL-02 |
| [OC-FILTER-005](#oc-filter-005) | 객체 lifecycle에 지정한 활동들이 나타나는 관측만 선택하는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [OC-FILTER-006](#oc-filter-006) | EOG 성능 값이 조건에 맞는 이벤트만 선택하는가? | 대응 구현 없음 | 미구현 | FILTER-01, PERF-02 |
| [OC-FILTER-007](#oc-filter-007) | 빈도나 활동 sequence로 실행 variant를 선택하는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03, OCEXEC-03 |
| [OC-DATA-001](#oc-data-001) | OCEL을 객체형별 case log로 투영하고 활동별 객체 수를 얻는가? | 부분 대응 | 일부 의미 겹침 | IO-02, STAT-01, OCEXEC-02 |
| [OC-DATA-002](#oc-data-002) | Succinct/exploded 표를 변환하고 활동·경로 빈도를 정리하는가? | 부분 대응 | 일부 의미 겹침 | IO-05, FILTER-01, STAT-02 |
| [OC-DATA-003](#oc-data-003) | 여러 OCEL을 합치거나 실행을 표본 선택하고 참조 객체를 정리하는가? | 대응 구현 없음 | 미구현 | IO-05, FILTER-01, FILTER-02, FILTER-03 |
| [OC-RULE-001](#oc-rule-001) | 객체형별 두 활동의 causal·concurrent·choice·skip 강도가 규칙을 만족하는가? | 부분 대응 | 일부 의미 겹침 | RULE-01, RULE-02 |
| [OC-RULE-002](#oc-rule-002) | 활동 이벤트의 객체 부재·참여·한 개·여러 개 비율이 규칙을 만족하는가? | 대응 구현 없음 | 미구현 | RULE-01, RULE-02 |
| [OC-RULE-003](#oc-rule-003) | 모델의 진단 성능값이 지정한 비교식·threshold를 만족하는가? | 대응 구현 없음 | 미구현 | RULE-02, PERF-05 |
| [OC-RULE-004](#oc-rule-004) | 확장 constraint graph의 OA·AA·AOA 규칙과 성능 조합을 평가하는가? | 부분 대응 | 일부 의미 겹침 | RULE-01, RULE-02, RULE-03 |
| [OC-RULE-005](#oc-rule-005) | 활동 존재·부재·동시 존재·배타·선택·XOR를 만족하는 객체와 비율은 무엇인가? | 부분 대응 | 일부 의미 겹침 | RULE-01, RULE-03, STAT-02 |
| [OC-RULE-006](#oc-rule-006) | 객체별 followed-by·directly-followed-by·precedence·block 조건의 대상과 비율은 무엇인가? | 부분 대응 | 일부 의미 겹침 | RULE-01, RULE-03, OCEXEC-02 |
| [OC-RULE-007](#oc-rule-007) | 활동 이벤트의 객체 참여 cardinality와 객체형별 관계 강도는 얼마인가? | 대응 구현 없음 | 미구현 | STAT-01, STAT-02, RULE-01 |
| [OC-RULE-008](#oc-rule-008) | Constraint graph 구조를 데이터에서 만들고 규칙 근거로 연결할 수 있는가? | 대응 구현 없음 | 미구현 | RULE-01, MODEL-01, VIEW-02 |
| [OC-REL-001](#oc-rel-001) | 특정 E2O qualifier로 참여한 객체 속성이 허용 조건에 맞는가? | 부분 대응 | 일부 의미 겹침 | REL-01, REL-02, REL-03 |
| [OC-REL-002](#oc-rel-002) | 이벤트에 참여한 source×target 객체 쌍의 O2O qualifier가 허용 관계인가? | 부분 대응 | 일부 의미 겹침 | REL-01, REL-03 |
| [OC-REL-003](#oc-rel-003) | 객체 속성 변화의 시간 순서와 이벤트 시점 값을 확인할 수 있는가? | 부분 대응 | 일부 의미 겹침 | REL-02, VIEW-01, VIEW-02 |
| [OC-FEAT-001](#oc-feat-001) | 이벤트 시점에 활동·객체·이전 행동·속성의 feature를 만들 수 있는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [OC-FEAT-002](#oc-feat-002) | Service·실행 기간·elapsed·remaining·synchronization 등의 event feature를 만들 수 있는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, PERF-01, PERF-02 |
| [OC-FEAT-003](#oc-feat-003) | 현재 자원·전체 workload와 이벤트 자원 feature는 무엇인가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, ORG-03 |
| [OC-FEAT-004](#oc-feat-004) | 실행별 크기·경계·기간·객체·활동·서비스 feature는 무엇인가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, PERF-04 |
| [OC-FEAT-005](#oc-feat-005) | Event/execution feature를 graph로 저장하고 train/test 변환을 fit할 수 있는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [OC-FEAT-006](#oc-feat-006) | Feature graph를 event 행의 표로 인코딩하는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [OC-FEAT-007](#oc-feat-007) | Feature를 sequence와 길이 k 학습 표본/target으로 만드는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [OC-FEAT-008](#oc-feat-008) | 시간창별 event/execution feature를 집계한 시계열을 만드는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, PERF-04 |
| [OC-FEAT-009](#oc-feat-009) | Feature 표준화·선형 회귀·MAE 계산을 제공하는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, SCOPE-04 |
| [OC-ACT-001](#oc-act-001) | Constraint interval pattern에 맞는 action 후보를 찾는가? | 대응 구현 없음 | 미구현 | ACT-01, RULE-02 |
| [OC-ACT-002](#oc-act-002) | 후보 action들의 선행·충돌 조건을 지키는 일정과 waiting/flow/makespan은 무엇인가? | 대응 구현 없음 | 미구현 | ACT-02, QA-03 |
| [OC-ACT-003](#oc-act-003) | Action이 구조상 전후 활동과 객체형에 미치는 영향 범위는 무엇인가? | 대응 구현 없음 | 미구현 | ACT-03, MODEL-06 |
| [OC-ACT-004](#oc-act-004) | Action 시점의 marking과 관련 subnet에 어떤 객체가 영향을 받는가? | 대응 구현 없음 | 미구현 | ACT-03, OCONF-02, MODEL-06 |
| [OC-ACT-005](#oc-act-005) | Action 전후 관측창에서 활동·객체 성능이 얼마나 달라졌는가? | 대응 구현 없음 | 미구현 | ACT-03, PERF-02, PERF-04 |
| [OC-ACT-006](#oc-act-006) | Constraint instance와 action interface의 설정을 교환하고 변경을 계산하는가? | 대응 구현 없음 | 미구현 | ACT-01, ACT-02, SCOPE-03 |
| [OC-IO-001](#oc-io-001) | 기존 OCEL 1 JSON/XML 데이터를 의미를 보존해 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05 |
| [OC-IO-002](#oc-io-002) | OCEL 2 XML/SQLite의 E2O/O2O qualifier와 객체 변경 이력을 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05, REL-01, REL-02 |
| [OC-IO-003](#oc-io-003) | CSV의 활동·시각·객체 열을 매핑하고 별도 객체 속성표를 입력할 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-01, IO-05 |
| [OC-IO-004](#oc-io-004) | OCEL object 표현과 dataframe/CSV 표현을 서로 바꿀 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-04, IO-05 |
| [OC-IO-005](#oc-io-005) | OCPA가 쓰는 OCEL 1 JSON 파일로 다시 출력할 수 있는가? | 대응 구현 없음 | 미구현 | IO-04, IO-05 |
| [OC-VIEW-001](#oc-view-001) | OCPN의 제어 흐름·성능 annotation·객체 구분을 읽기 쉬운 graph로 보여주는가? | 부분 대응 | 일부 의미 겹침 | VIEW-01, VIEW-02, VIEW-03 |
| [OC-VIEW-002](#oc-view-002) | Constraint graph의 활동·객체·수식·규칙 edge를 시각화하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, RULE-01 |
| [OC-VIEW-003](#oc-view-003) | 객체별 variant 실행을 chevron sequence 등으로 탐색할 수 있는가? | 대응 구현 없음 | 미구현 | VIEW-02, VIEW-03, OCEXEC-03 |
| [OC-VIEW-004](#oc-view-004) | Joint alignment의 log/model/synchronous move와 객체 참여를 시각적으로 따라갈 수 있는가? | 부분 대응 | 일부 의미 겹침 | VIEW-01, VIEW-02, OCONF-04 |
| [OC-DATA-004](#oc-data-004) | 이벤트-객체 조회와 특정 활동을 포함하거나 잇는 객체 수를 계산하는가? | 부분 대응 | 일부 의미 겹침 | STAT-01, STAT-02, REL-01 |

## OC-EXEC-001

**공유 객체로 연결된 이벤트를 하나의 실행으로 묶으면 어떤 실행과 미배정 이벤트가 생기는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 분석 대상 객체형·관계 범위 |
| 확인할 출력 | 연결 실행별 event/object ID, 미배정·고립 대상과 coverage |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체형 선택·무관계 이벤트·eventless object·공유 Agent로 인한 거대 실행의 경계와 OCPA 대응 사례를 확정. |
| 다음 작업 ID | OCEXEC-01, OCEXEC-04 |
| 의미·옵션·한계 | CONN_COMP='connected_components'. PIX가 O2O를 실행 연결에 사용한다는 뜻은 아니다. |

**현재 PIX 근거:** `discover_executions`.
소스: [src/pix/compute/executions.py](../../../src/pix/compute/executions.py), [src/pix/contracts/execution.py](../../../src/pix/contracts/execution.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/process_executions/versions/connected_components.py :: apply`
- `ocpa/algo/util/process_executions/factory.py :: apply` — facade
- 변형 `ocpa/algo/util/process_executions/factory.py :: VERSIONS` → `CONN_COMP`
  - 등록 이름 `CONN_COMP` / 상수·키 `CONN_COMP` / 대상 `connected_components.apply`

## OC-EXEC-002

**지정한 leading 객체를 중심으로 어떤 객체·이벤트가 실행에 포함되고 실행끼리 얼마나 겹치는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, leading 객체형, 확장 규칙 |
| 확인할 출력 | Leading 객체별 실행·포함 객체와 이벤트, 실행 간 overlap |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | Leading-type 확장 규칙의 차이와 overlap·unassigned 모집단을 대조. |
| 다음 작업 ID | OCEXEC-01, OCEXEC-04 |
| 의미·옵션·한계 | LEAD_TYPE='leading_type'. 동일한 이름만으로 경계 동치를 확정하지 않는다. |

**현재 PIX 근거:** `discover_executions`.
소스: [src/pix/compute/executions.py](../../../src/pix/compute/executions.py), [src/pix/contracts/execution.py](../../../src/pix/contracts/execution.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/process_executions/versions/leading_type.py :: apply`
- 변형 `ocpa/algo/util/process_executions/factory.py :: VERSIONS` → `LEAD_TYPE`
  - 등록 이름 `LEAD_TYPE` / 상수·키 `LEAD_TYPE` / 대상 `leading_type.apply`

## OC-EXEC-003

**객체의 이벤트 순서를 어떤 직접 후속 관계 graph로 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 또는 table/raw event 표현, 순서·qualifier 정책 |
| 확인할 출력 | Event 노드와 객체별 후속 edge를 가진 EOG 및 원본 매핑 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Table 행 순서 EOG, raw event graph, timestamp/ID 규칙의 차이와 qualifier edge 정보를 명시. |
| 다음 작업 ID | OCEXEC-02, OCEXEC-03 |
| 의미·옵션·한계 | CLASSIC='classic'. PIX 기본 동시각 유보 정책과 원본 table 순서는 다르며, EOG를 인과 관계로 확대하지 않는다. |

**현재 PIX 근거:** `reconstruct_traces`, `discover_ocdfg`.
소스: [src/pix/compute/trace.py](../../../src/pix/compute/trace.py), [src/pix/compute/ocdfg.py](../../../src/pix/compute/ocdfg.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/variants/util/table.py :: eog_from_log`
- `ocpa/algo/util/retrieval/event_graph/algorithm.py :: apply`
- `ocpa/objects/graph/event_graph/retrieval/algorithm.py :: apply`
- 변형 `ocpa/algo/util/retrieval/event_graph/algorithm.py :: VERSIONS` → `classic`
  - 등록 이름 `classic` / 상수·키 `CLASSIC` / 대상 `classic.apply`

## OC-EXEC-004

**두 실행의 활동·객체 참여 graph가 같은 variant인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 실행별 EOG/객체 참여, exact 옵션·시간/상태 한도 |
| 확인할 출력 | Variant 동치 집단·빈도·대표 graph와 판정 완료 범위 |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCPA EOG 라벨/edge type 동치와 PIX incidence 동치의 대응 profile 및 반례, approximate hash 결과의 별도 상태를 구현. |
| 다음 작업 ID | OCEXEC-03, OCEXEC-04 |
| 의미·옵션·한계 | TWO_PHASE='two_phase'. OCPA 기본 exact_variant_calculation=False는 WL hash 분류; PIX는 bounded exact incidence 검사. 두 동치 정의가 같다는 증거는 없다. |

**현재 PIX 근거:** `discover_variants`.
소스: [src/pix/compute/variants.py](../../../src/pix/compute/variants.py), [src/pix/contracts/execution.py](../../../src/pix/contracts/execution.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/variants/versions/twophase.py :: apply`
- `ocpa/algo/util/variants/factory.py :: apply` — facade
- 변형 `ocpa/algo/util/variants/factory.py :: VERSIONS` → `TWO_PHASE`
  - 등록 이름 `TWO_PHASE` / 상수·키 `TWO_PHASE` / 대상 `twophase.apply`

## OC-EXEC-005

**전수 graph 동형 비교로 실행 variant를 분류할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 실행 graph 집합, node/edge 동치 조건·timeout |
| 확인할 출력 | 동형 관계로 나눈 variant 집단·빈도·대표 graph |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | One-phase 정의의 대응 여부와 동일라벨 대칭 graph, timeout 처리 검산. |
| 다음 작업 ID | OCEXEC-03, OCEXEC-04 |
| 의미·옵션·한계 | ONE_PHASE='one_phase'. 원본에 subclass_mappings[subclass_counter] append와 순회 중 dict 변경 코드가 있다. 원본 결과를 무조건 정답으로 쓰지 않는다. |

**현재 PIX 근거:** `discover_variants`.
소스: [src/pix/compute/variants.py](../../../src/pix/compute/variants.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/variants/versions/onephase.py :: apply`
- 변형 `ocpa/algo/util/variants/factory.py :: VERSIONS` → `ONE_PHASE`
  - 등록 이름 `ONE_PHASE` / 상수·키 `ONE_PHASE` / 대상 `onephase.apply`

## OC-DISC-001

**객체별 관측 흐름을 통합해 공동 참여와 variable arc를 가진 OCPN을 찾는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 객체형별 발견 및 variable arc 정책 |
| 확인할 출력 | OCPN·형별 모델 매핑·관측 cardinality와 수용 근거 |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | Current new_inductive의 per-type 발견·merge·variable arc 판정과 자체 OCPN 발견의 의미 대조; 잡음 miner 확장. |
| 다음 작업 ID | DISC-01, DISC-02, OCONF-04 |
| 의미·옵션·한계 | INDUCTIVE='inductive'는 new_inductive.apply만 가리킴. PIX의 joint accepting witness/observed cardinality를 규범 cardinality나 전체 soundness로 해석하지 않음. |

**현재 PIX 근거:** `discover_ocpn`.
소스: [src/pix/compute/ocpn_discovery.py](../../../src/pix/compute/ocpn_discovery.py), [src/pix/contracts/ocpn_discovery.py](../../../src/pix/contracts/ocpn_discovery.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/discovery/ocpn/algorithm.py :: apply`
- `ocpa/algo/discovery/ocpn/versions/new_inductive.py :: apply`
- `ocpa/algo/discovery/ocpn/versions/new_inductive.py :: discover_nets`
- `ocpa/algo/discovery/ocpn/versions/new_inductive.py :: discover_inductive`
- 변형 `ocpa/algo/discovery/ocpn/algorithm.py :: VERSIONS` → `inductive`
  - 등록 이름 `inductive` / 상수·키 `INDUCTIVE` / 대상 `new_inductive.apply`

## OC-DISC-002

**예전 OCPN 발견 경로의 Alpha·IM·DFG miner 선택은 어떤 통합 모델을 만드는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 dataframe, per-type discovery callable, 빈도 threshold |
| 확인할 출력 | 객체형별 net·object count 및 통합 OCPN |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Factory 미등록 직접 호출 경로를 inventory에 보존하고 Alpha·DFG→net·reduction 조합을 native로 연결. |
| 다음 작업 ID | DISC-01, DISC-03, MODEL-04 |
| 의미·옵션·한계 | discovery_algorithm callable은 extension point이며 유한한 variant 목록이 아니다. OCPA의 PM4Py backend 호출을 PIX runtime 의존성으로 들여오지 않음. |

**현재 PIX 근거:** `discover_ocpn`, `discover_process_tree`, `discover_dfg`.
소스: [src/pix/compute/ocpn_discovery.py](../../../src/pix/compute/ocpn_discovery.py), [src/pix/compute/discovery.py](../../../src/pix/compute/discovery.py), [src/pix/compute/dfg.py](../../../src/pix/compute/dfg.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md), [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/discovery/ocpn/versions/inductive.py :: apply`
- `ocpa/algo/discovery/ocpn/versions/inductive.py :: discover_nets`
- `ocpa/algo/discovery/ocpn/versions/inductive.py :: discover_alpha`
- `ocpa/algo/discovery/ocpn/versions/inductive.py :: discover_inductive`
- `ocpa/algo/discovery/ocpn/versions/inductive.py :: discover_dfg_miner`
- `ocpa/algo/discovery/ocpn/versions/inductive.py :: reduce_petri_net`

## OC-DISC-003

**발견한 OCPN에 성능 진단을 결합한 enhanced 모델을 얻는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, OCEL, 성능 측정·집계 옵션 |
| 확인할 출력 | OCPN과 token 성능 diagnostics를 결합한 enhanced 모델 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OPERA 성능 결과와 원본 모델을 연결하는 annotation/진단 계약 구현. |
| 다음 작업 ID | MODEL-06, PERF-03, VIEW-02 |
| 의미·옵션·한계 | 새 control-flow miner가 아니라 OCPN + token performance의 합성 wrapper. 독립 알고리즘으로 중복 계산하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/discovery/enhanced_ocpn/algorithm.py :: apply`

## OC-CONF-001

**실행의 이벤트·객체 참여를 OCPN과 맞추는 최소 비용 joint alignment는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL execution/variant, OCPN, 비용·객체/순서 범위 |
| 확인할 출력 | Joint move sequence·binding·최종 marking·비용과 완료/한도 |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCPA variant 대표 평가·PX-net/synchronous product·variable cardinality 확장·비용을 PIX profile과 대조하고 witness·한도 검증 확대. |
| 다음 작업 ID | OCONF-01, OCONF-04 |
| 의미·옵션·한계 | Wheel 1.3.4에 실제 joint alignment 코드가 존재. PIX도 실제 공동 binding 탐색을 수행한다. 동일 목적함수·cardinality·모집단 동치는 미확정. reference_symbols의 support 항목은 cardinality·PX-net·synchronous product·binding·witness 구성 helper이며 별도 업무 알고리즘으로 세지 않는다. |

**현재 PIX 근거:** `align_object_log`.
소스: [src/pix/compute/object_conformance.py](../../../src/pix/compute/object_conformance.py), [src/pix/compute/object_bindings.py](../../../src/pix/compute/object_bindings.py), [src/pix/contracts/object_conformance.py](../../../src/pix/contracts/object_conformance.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/alignments/algorithm.py :: calculate_oc_alignments`
- `ocpa/algo/conformance/alignments/algorithm.py :: calculate_oc_alignment_given_variant_id`
- `ocpa/algo/conformance/alignments/algorithm.py :: dijkstra`
- `ocpa/algo/conformance/alignments/algorithm.py :: get_all_event_objects` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: get_in_cardinality_of_transition` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: get_out_cardinality_of_transition` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: get_in_cardinality_of_transition_px` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: get_out_cardinality_of_transition_px` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: get_properties_of_transition` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: set_properties_of_transition` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: get_properties_of_place` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: set_properties_of_place` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: process_execution_net_from_process_execution` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: create_all_transitions` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: preprocessing_dejure_net` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: create_synchronous_product_net` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: alignment_from_dijkstra` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: create_all_bindings` — support
- `ocpa/algo/conformance/alignments/algorithm.py :: all_valid_bindings` — support

## OC-CONF-002

**공동 객체 흐름의 missing/remaining/consumed/produced token과 fitness는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, OCPN, silent/flooding/replay 설정 |
| 확인할 출력 | 객체 token p/c/m/r, fitness, 객체·place별 보정 진단 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Object-centric token replay, backward silent 탐색, 최종 token 수집·flooding·fitness를 native 구현. |
| 다음 작업 ID | OCONF-02, OCONF-04 |
| 의미·옵션·한계 | PIX joint alignment가 존재해도 replay 정의를 대체한 것은 아님. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/token_based_replay/algorithm.py :: apply`
- `ocpa/algo/conformance/token_based_replay/variants/object_centric_replay.py :: apply`
- 변형 `ocpa/algo/conformance/token_based_replay/algorithm.py :: method` → `object_centric`
  - 등록 이름 `object_centric` / 상수·키 `'object_centric'` / 대상 ``

## OC-CONF-003

**객체형별로 평탄화한 replay 점수를 합산하면 어떤 fitness가 나오는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, OCPN의 객체형 projection, replay 설정 |
| 확인할 출력 | Flattened replay 합계 p/c/m/r와 정규화 fitness |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCPN type projection, flat replay의 합계 p/c/m/r와 정규화 수식·설정 대조. |
| 다음 작업 ID | OCONF-02, CONF-02, MODEL-06 |
| 의미·옵션·한계 | OCPA는 PM4Py flattened token replay를 호출. PIX에 classical token counts는 있으나 OCPN projection/동일 총합 fitness 공개 연산은 없음. |

**현재 PIX 근거:** `reconstruct_traces`, `replay_traces`.
소스: [src/pix/compute/trace.py](../../../src/pix/compute/trace.py), [src/pix/compute/replay.py](../../../src/pix/compute/replay.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/token_based_replay/variants/flattened_replay.py :: apply`
- 변형 `ocpa/algo/conformance/token_based_replay/algorithm.py :: method` → `flattened`
  - 등록 이름 `flattened` / 상수·키 `'flattened'` / 대상 ``

## OC-CONF-004

**객체별 과거 context에서 로그와 모델의 가능한 다음 활동이 얼마나 일치하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, OCPN, 선택적 사전 계산 context/binding |
| 확인할 출력 | Context precision·fitness와 평가/제외 모집단 |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCPA context multiset·enabled activities·event 평균·skip 정책에 대응하는 별도 지표 profile 구현. |
| 다음 작업 ID | OCONF-03, OCONF-04 |
| 의미·옵션·한계 | 현재 PIX binding_prefix.v1은 concrete binding-prefix micro 지표이고 OCPA event-averaged activity-context 지표가 아니다. 같은 precision/fitness 이름으로 수치 호환을 주장하지 않는다. |

**현재 PIX 근거:** `measure_object_context`.
소스: [src/pix/compute/object_context.py](../../../src/pix/compute/object_context.py), [src/pix/contracts/object_context.py](../../../src/pix/contracts/object_context.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/precision_and_fitness/evaluator.py :: apply`
- `ocpa/algo/conformance/precision_and_fitness/utils.py :: calculate_contexts_and_bindings`
- `ocpa/algo/conformance/precision_and_fitness/variants/replay_context.py :: enabled_log_activities`
- `ocpa/algo/conformance/precision_and_fitness/variants/replay_context.py :: enabled_model_activities_multiprocessing`
- `ocpa/algo/conformance/precision_and_fitness/variants/replay_context.py :: calculate_precision_and_fitness`

## OC-CONF-005

**Silent transition 경로와 token flooding을 replay에서 어떤 정책으로 다루는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Marking, 대상 객체/transition, silent graph와 cache |
| 확인할 출력 | Silent 경로·변경 marking·token 보정과 탐색 종료 상태 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Backward tree·shortest-path 정책, caching과 S-component/token reset flooding 대조. |
| 다음 작업 ID | OCONF-02, QA-03 |
| 의미·옵션·한계 | 독립 업무 지표보다 OC-CONF-002의 알고리즘/최적화 정책. 오타 cashed_bst_backward_replay는 실제 공개 symbol 그대로 기록. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/token_based_replay/backward_replay/algorithm.py :: bst_backward_replay`
- `ocpa/algo/conformance/token_based_replay/backward_replay/algorithm.py :: cashed_bst_backward_replay`
- `ocpa/algo/conformance/token_based_replay/backward_replay/algorithm.py :: shortest_path_backward_replay`
- `ocpa/algo/conformance/token_based_replay/enhancement/address_token_flooding.py :: solve_token_flooding`
- `ocpa/algo/conformance/token_based_replay/enhancement/address_token_flooding.py :: calculate_S_component`
- `ocpa/algo/conformance/token_based_replay/enhancement/activity_caching.py :: check_activity_caching`
- `ocpa/algo/conformance/token_based_replay/backward_replay/algorithm.py :: execute_silence_sequence` — support

## OC-PERF-001

**이벤트의 선행 입력 도착 차이로 flow·sojourn·synchronization·pooling·lagging·readiness를 계산하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL EOG, 활동·객체형, 측정·집계 선택 |
| 확인할 출력 | flow/sojourn/synchronization/pooling/lagging/readiness 표본·집계 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 각 수식의 predecessor/객체형 선택·초기 이벤트·결측 정의와 독립 검산을 구현. |
| 다음 작업 ID | PERF-01, PERF-02 |
| 의미·옵션·한계 | EVENT_OBJECT_GRAPH='event_object_graph_based'. 'rediness'는 실제 registry 오타. PIX event gap만으로 EOG 전체 지표를 구현했다고 보지 않음. readiness_time의 들여쓰기와 특정 객체형 predecessor 부재 오류를 참조 정답에 복제하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: apply`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: flow_time`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: sojourn_time`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: synchronization_time`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: pooling_time`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: lagging_time`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: readiness_time`
- `ocpa/algo/enhancement/event_graph_based_performance/algorithm.py :: apply` — facade
- 변형 `ocpa/algo/enhancement/event_graph_based_performance/algorithm.py :: VERSIONS` → `event_object_graph_based`
  - 등록 이름 `event_object_graph_based` / 상수·키 `EVENT_OBJECT_GRAPH` / 대상 `event_object_graph_based.apply`
- 변형 `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: measure_function_mapping` → `flow`, `sojourn`, `synchronization`, `pooling`, `lagging`, `rediness`
  - 등록 이름 `flow` / 상수·키 `'flow'` / 대상 `flow_time`
  - 등록 이름 `sojourn` / 상수·키 `'sojourn'` / 대상 `sojourn_time`
  - 등록 이름 `synchronization` / 상수·키 `'synchronization'` / 대상 `synchronization_time`
  - 등록 이름 `pooling` / 상수·키 `'pooling'` / 대상 `pooling_time`
  - 등록 이름 `lagging` / 상수·키 `'lagging'` / 대상 `lagging_time`
  - 등록 이름 `rediness` / 상수·키 `'rediness'` / 대상 `readiness_time`

## OC-PERF-002

**EOG에서 특정 활동의 elapsed/remaining 시간이 어떤 구간을 뜻하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL EOG, 활동·객체형·집계 |
| 확인할 출력 | 참조의 인접 선행/후속 기준 elapsed/remaining 표본·집계 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 원본 함수의 인접 선행/후속 수식과 전체 실행 prefix/remaining 구간을 별도 정의. |
| 다음 작업 ID | PERF-01, PERF-02, PERF-04 |
| 의미·옵션·한계 | 원본 elapsed는 직전 predecessor의 최대 시각과 차이이며 global case elapsed가 아님. PIX 객체 trace event gap과 부분적으로 겹치지만 같은 모집단·집계는 미구현. |

**현재 PIX 근거:** `measure_temporal`.
소스: [src/pix/compute/temporal.py](../../../src/pix/compute/temporal.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: elapsed_time`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: remaining_time`
- 변형 `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: measure_function_mapping` → `elapsed`, `remaining`
  - 등록 이름 `elapsed` / 상수·키 `'elapsed'` / 대상 `elapsed_time`
  - 등록 이름 `remaining` / 상수·키 `'remaining'` / 대상 `remaining_time`

## OC-PERF-003

**활동에 참여한 객체 수와 객체별 활동 발생 수의 분포는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 활동·객체형·집계 |
| 확인할 출력 | Event별 객체 수 또는 객체별 활동 수 분포와 요약값 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Event별 객체 count와 객체별 activity count의 모집단/집계·0 관측 포함 정의를 구현. |
| 다음 작업 ID | STAT-01, STAT-02, PERF-01 |
| 의미·옵션·한계 | 기초 count 재료가 있어도 참조 분포/집계 공개 연산은 없음. |

**현재 PIX 근거:** `discover_ocdfg`, `reconstruct_traces`.
소스: [src/pix/compute/ocdfg.py](../../../src/pix/compute/ocdfg.py), [src/pix/compute/trace.py](../../../src/pix/compute/trace.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: object_freq`
- `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: act_freq`
- 변형 `ocpa/algo/enhancement/event_graph_based_performance/versions/event_object_graph_based.py :: measure_function_mapping` → `object_freq`, `act_freq`
  - 등록 이름 `object_freq` / 상수·키 `'object_freq'` / 대상 `object_freq`
  - 등록 이름 `act_freq` / 상수·키 `'act_freq'` / 대상 `act_freq`

## OC-PERF-004

**Replay token 도착과 실제 시작·완료를 연결한 OPERA 성능은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, OCEL의 start/complete, token replay·집계 설정 |
| 확인할 출력 | TokenVisit에 연결된 시간 표본과 활동/객체형 성능 diagnostics |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | TokenVisit/event 대응, waiting/service/sojourn/synchronization/pooling/lagging/flow와 보정 token의 시간 처리 구현. |
| 다음 작업 ID | PERF-01, PERF-03, PERF-05 |
| 의미·옵션·한계 | OPERA='opera'. PIX에 관측 service time과 classical replay는 있으나 결합 token-time 계산은 없음. OCPA waiting=min token 도착 기준과 all-input-ready 기준을 혼동하지 않는다. |

**현재 PIX 근거:** `measure_temporal`, `replay_traces`.
소스: [src/pix/compute/temporal.py](../../../src/pix/compute/temporal.py), [src/pix/compute/replay.py](../../../src/pix/compute/replay.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: apply`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.analyze`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.measure_waiting`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.measure_service`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.measure_sojourn`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.measure_synchronization`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.measure_pooling`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: PerformanceAnalysis.measure_lagging`
- `ocpa/algo/enhancement/token_replay_based_performance/algorithm.py :: apply` — facade
- 변형 `ocpa/algo/enhancement/token_replay_based_performance/algorithm.py :: VERSIONS` → `opera`
  - 등록 이름 `opera` / 상수·키 `OPERA` / 대상 `opera.apply`

## OC-PERF-005

**모델 activity·arc 빈도와 객체 참여/fitness 진단을 어떻게 집계·annotation하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Replay diagnostics, 모델 매핑, 집계 선택 |
| 확인할 출력 | Activity/arc 빈도·object count·place fitness annotation |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Replay의 place/arc/activity/객체 count 출처, 동일label 노드 구분, 진단 aggregation/annotation 구현. |
| 다음 작업 ID | PERF-03, MODEL-06, VIEW-02 |
| 의미·옵션·한계 | OC-PERF-004의 결과 조합 경로. 독립 miner로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: aggregate_frequencies`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: transform_diagnostics`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: merge_replay`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: merge_place_fitness`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: merge_act_freq`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: new_merge_object_count`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: merge_object_count`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: agg_merged_object_count`

## OC-PERF-006

**성능 표본을 평균·중앙값·표준편차·합·최소·최대로 요약하면 어떤 값인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동/객체형별 수치 표본, 집계 종류 |
| 확인할 출력 | Mean/median/stdev/sum/min/max, 모집단 크기·결측 근거 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 빈 표본·1개 표본·가중치·모집단을 명시한 aggregation 제공. |
| 다음 작업 ID | PERF-01, STAT-03 |
| 의미·옵션·한계 | OPERA 내부 명칭은 mean/median/stdev/sum/min/max, EOG util AGG_MAP은 avg/med/std/sum/min/max. 같은 지표 wrapper의 이름 차이와 singleton 처리 차이를 보존. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: aggregate_stats`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: aggregate_ot_stats`
- `ocpa/algo/enhancement/token_replay_based_performance/versions/opera.py :: aggregate_perf_records`
- 변형 `ocpa/util/util.py :: AGG_MAP` → `avg`, `med`, `std`, `sum`, `min`, `max`
  - 등록 이름 `avg` / 상수·키 `'avg'` / 대상 ``
  - 등록 이름 `med` / 상수·키 `'med'` / 대상 ``
  - 등록 이름 `std` / 상수·키 `'std'` / 대상 ``
  - 등록 이름 `sum` / 상수·키 `'sum'` / 대상 ``
  - 등록 이름 `min` / 상수·키 `'min'` / 대상 ``
  - 등록 이름 `max` / 상수·키 `'max'` / 대상 ``

## OC-MODEL-001

**OCPN place·transition·arc·marking과 변경을 표현하고 저장할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Place/transition/arc/marking과 ID, 명시 변경 |
| 확인할 출력 | OCPN 구조·marking·조회 결과·직렬화 표현 |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | Immutable PIX 모델을 기준으로 OCPA model/mapping 요구를 대응하고 mutation wrapper의 대체 경계 명시. |
| 다음 작업 ID | MODEL-01, MODEL-03 |
| 의미·옵션·한계 | OCPA semantics.py는 비어 있음. 그것을 미구현 알고리즘으로 세지 않는다. PIX는 유한 객체 universe·unit arc/명시 cardinality profile을 가진 실제 발화 의미를 제공. |

**현재 PIX 근거:** `model_document`, `read_model`, `write_model`, `is_binding_enabled`, `fire_binding`, `is_object_final`.
소스: [src/pix/contracts/models.py](../../../src/pix/contracts/models.py), [src/pix/models.py](../../../src/pix/models.py), [src/pix/compute/model_semantics.py](../../../src/pix/compute/model_semantics.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet`
- `ocpa/objects/oc_petri_net/obj.py :: Marking`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.add_arc`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.remove_place`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.remove_arc`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.remove_arcs`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.add_arcs`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.remove_transition`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.find_arc`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.find_transition`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.find_place`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.to_dict`

## OC-MODEL-002

**객체형별로 특정 활동의 선행·후행 노드와 두 활동 사이 subnet을 구할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, 객체형, 기준 활동 또는 source/target |
| 확인할 출력 | Ancestor/descendant place·transition 집합 또는 subnet |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 원본 node ID 대응이 있는 graph traversal·subnet 계산 구현. |
| 다음 작업 ID | MODEL-05, MODEL-06 |
| 의미·옵션·한계 | 원본은 per-type PM4Py net와 mapping을 참조. PIX의 모델 존재만으로 조회 알고리즘까지 있다고 세지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.ancestor_transitions`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.ancestor_places`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.descendant_transitions`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.descendant_places`
- `ocpa/objects/oc_petri_net/obj.py :: ObjectCentricPetriNet.subnet`

## OC-MODEL-003

**객체형·subprocess로 OCPN을 투영하거나 일부 활동을 숨길 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, 객체형/구간/숨길 활동 선택 |
| 확인할 출력 | 투영 또는 숨김 처리 모델과 원본 요소 매핑·손실/보존 설명 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Type projection, source-target subprocess, hiding/reduction의 보존 성질과 원본 매핑 구현. |
| 다음 작업 ID | MODEL-06 |
| 의미·옵션·한계 | OBJECT_TYPES='object_types', SUBPROCESS='subprocess', HIDING='hiding'. Viewer 숨김은 계산상의 model projection 대체가 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/ocpn_analysis/projection/algorithm.py :: apply`
- `ocpa/algo/enhancement/ocpn_analysis/projection/versions/project_on_subprocess.py :: apply`
- `ocpa/algo/enhancement/ocpn_analysis/projection/versions/project_on_subprocess.py :: old_apply`
- `ocpa/algo/enhancement/ocpn_analysis/projection/versions/project_on_object_types.py :: apply`
- `ocpa/algo/enhancement/ocpn_analysis/projection/versions/hide.py :: apply`
- 변형 `ocpa/algo/enhancement/ocpn_analysis/projection/algorithm.py :: VERSIONS` → `object_types`, `subprocess`, `hiding`
  - 등록 이름 `object_types` / 상수·키 `OBJECT_TYPES` / 대상 `project_on_object_types.apply`
  - 등록 이름 `subprocess` / 상수·키 `SUBPROCESS` / 대상 `project_on_subprocess.apply`
  - 등록 이름 `hiding` / 상수·키 `HIDING` / 대상 `hide.apply`

## OC-MODEL-004

**보존 조건 아래 OCPN의 불필요한 place·transition을 줄일 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, 보존할 visible·초기/최종 노드 |
| 확인할 출력 | 축약 OCPN, 적용 rule 및 보존 조건 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 여섯 reduction rule의 적용 조건·변경 기록·보존 관계 및 반례 검증 구현. |
| 다음 작업 ID | MODEL-06, QA-01 |
| 의미·옵션·한계 | MURATA='murata'. 단순 그림 축소가 아니라 계산 모델 변경. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: apply`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: FST`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: FSP`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: FPT`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: FPP`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: EST`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/versions/murata.py :: ESP`
- `ocpa/algo/enhancement/ocpn_analysis/reduction/algorithm.py :: apply` — facade
- 변형 `ocpa/algo/enhancement/ocpn_analysis/reduction/algorithm.py :: VERSIONS` → `murata`
  - 등록 이름 `murata` / 상수·키 `MURATA` / 대상 `murata.apply`

## OC-MODEL-005

**선택 활동과 객체형이 subprocess의 참여 조건을 만족하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, 선택 활동·객체형 |
| 확인할 출력 | Subprocess와 제한된 incidence 충족 여부 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 선택된 객체형과 transition incidence 조건을 명시된 이름으로 평가. |
| 다음 작업 ID | MODEL-01, MODEL-05, MODEL-06 |
| 의미·옵션·한계 | OCPA Subprocess.sound는 선택 transition에 객체형 incident place가 있는지 확인하는 제한 검사이다. 일반 WF-net/OCPN soundness 알고리즘이 구현된 것으로 기록하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/oc_petri_net/obj.py :: Subprocess`
- `ocpa/objects/oc_petri_net/obj.py :: Subprocess.sound`

## OC-FILTER-001

**빈도가 낮은 활동·variant나 선택하지 않은 실행을 제거할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 빈도 threshold 또는 execution 목록 |
| 확인할 출력 | 선택 sublog와 포함/제외·관계 정리 근거 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동 빈도/누적 variant 빈도 threshold와 선택 execution의 참조·분모 보존 구현. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/activity_filtering.py :: filter_infrequent_activities`
- `ocpa/algo/util/filtering/log/variant_filtering.py :: filter_infrequent_variants`
- `ocpa/algo/util/filtering/log/case_filtering.py :: filter_process_executions`

## OC-FILTER-002

**시간창에 시작·끝·포함·겹침 조건을 만족하는 실행 또는 이벤트만 선택하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 시간창, start/end/spanning/contained/events 선택 |
| 확인할 출력 | 시간 조건을 만족한 실행 또는 event sublog |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 시간창 경계·미완료·기존 상태·원본순서와 관계를 보존하는 temporal filtering 구현. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 동일 목적의 별도 index 기반 구현 경로도 보존. start/end/spanning/contained/events 의미를 개별 검산. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/time_filtering.py :: start`
- `ocpa/algo/util/filtering/log/time_filtering.py :: spanning`
- `ocpa/algo/util/filtering/log/time_filtering.py :: end`
- `ocpa/algo/util/filtering/log/time_filtering.py :: contained`
- `ocpa/algo/util/filtering/log/time_filtering.py :: extract_sublog`
- `ocpa/algo/util/filtering/log/time_filtering.py :: events`
- `ocpa/algo/util/filtering/log/index_based_filtering.py :: time_filtering`

## OC-FILTER-003

**활동·객체형 목록이나 빈도로 OCEL을 선택하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 활동·객체형 집합 또는 빈도 threshold |
| 확인할 출력 | 선택 sublog 및 정리된 객체 참조 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 인덱스 기반 선택과 객체 참조 정리의 결과·성능을 구현. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/index_based_filtering.py :: activity_filtering`
- `ocpa/algo/util/filtering/log/index_based_filtering.py :: activity_freq_filtering`
- `ocpa/algo/util/filtering/log/index_based_filtering.py :: object_type_filtering`
- `ocpa/algo/util/filtering/log/index_based_filtering.py :: object_freq_filtering`

## OC-FILTER-004

**이벤트·객체 속성 조건을 만족하는 데이터만 남기는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 이벤트/객체 속성 조건 |
| 확인할 출력 | 조건에 맞는 sublog와 객체 이력·선택 lineage |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Attribute 조건·시점·결측과 객체 이력 경계 상태 보존 구현. |
| 다음 작업 ID | FILTER-01, FILTER-02, REL-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/index_based_filtering.py :: event_attribute_filtering`
- `ocpa/algo/util/filtering/log/index_based_filtering.py :: object_attribute_filtering`

## OC-FILTER-005

**객체 lifecycle에 지정한 활동들이 나타나는 관측만 선택하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 객체형, lifecycle 활동 조건 |
| 확인할 출력 | 조건을 만족하는 객체와 관련 event sublog |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동의 존재·순서 조건 및 부분 lifecycle의 모집단/관계 선택 검산. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/index_based_filtering.py :: object_lifecycle_filtering`

## OC-FILTER-006

**EOG 성능 값이 조건에 맞는 이벤트만 선택하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, EOG 성능 measure·threshold·객체형 |
| 확인할 출력 | 성능 조건을 만족하는 event sublog 및 측정 근거 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | flow/sojourn/synchronization/pooling/lagging/rediness/elapsed/remaining/object_freq 기준 선택을 공통 측정 결과와 연결. |
| 다음 작업 ID | FILTER-01, PERF-02 |
| 의미·옵션·한계 | 별도 nested metric 재구현은 공통 PERF 정의로 공유하되 원본 선택 기준 차이를 기록. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/index_based_filtering.py :: event_performance_based_filtering`
- 변형 `ocpa/algo/util/filtering/log/index_based_filtering.py :: measure_function_mapping` → `flow`, `sojourn`, `synchronization`, `pooling`, `lagging`, `rediness`, `elapsed`, `remaining`, `object_freq`
  - 등록 이름 `flow` / 상수·키 `'flow'` / 대상 `compute_flow_time`
  - 등록 이름 `sojourn` / 상수·키 `'sojourn'` / 대상 `compute_sojourn_time`
  - 등록 이름 `synchronization` / 상수·키 `'synchronization'` / 대상 `compute_synchronization_time`
  - 등록 이름 `pooling` / 상수·키 `'pooling'` / 대상 `compute_pooling_time`
  - 등록 이름 `lagging` / 상수·키 `'lagging'` / 대상 `compute_lagging_time`
  - 등록 이름 `rediness` / 상수·키 `'rediness'` / 대상 `compute_rediness_time`
  - 등록 이름 `elapsed` / 상수·키 `'elapsed'` / 대상 `compute_elapsed_time`
  - 등록 이름 `remaining` / 상수·키 `'remaining'` / 대상 `compute_remaining_time`
  - 등록 이름 `object_freq` / 상수·키 `'object_freq'` / 대상 `compute_object_freq`

## OC-FILTER-007

**빈도나 활동 sequence로 실행 variant를 선택하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL variant, threshold 또는 활동 sequence 목록 |
| 확인할 출력 | 선택 variant·실행·이벤트와 overlap/빈도 coverage |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | EOG variant와 activity sequence 조건을 구분한 필터 및 overlap 집계 구현. |
| 다음 작업 ID | FILTER-01, FILTER-03, OCEXEC-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/filtering/log/index_based_filtering.py :: variant_infrequent_filtering`
- `ocpa/algo/util/filtering/log/index_based_filtering.py :: variant_activity_sequence_filtering`

## OC-DATA-001

**OCEL을 객체형별 case log로 투영하고 활동별 객체 수를 얻는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL table, 기준 객체형·column mapping |
| 확인할 출력 | 객체별 case log와 활동별 객체 참여 count 분포 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체형별 source order/시각 동률/공유 이벤트 중복·count 분포를 명시적으로 연결. |
| 다음 작업 ID | IO-02, STAT-01, OCEXEC-02 |
| 의미·옵션·한계 | OCPA project_log는 PM4Py converter를 사용. PIX native trace 결과와 교환 형식 log 변환은 별개. |

**현재 PIX 근거:** `reconstruct_traces`.
소스: [src/pix/compute/trace.py](../../../src/pix/compute/trace.py), [src/pix/contracts/analysis.py](../../../src/pix/contracts/analysis.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/util.py :: project_log`
- `ocpa/algo/util/util.py :: project_log_with_object_count`

## OC-DATA-002

**Succinct/exploded 표를 변환하고 활동·경로 빈도를 정리하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Succinct/exploded 표, 빈도·경로·시각/객체 조건 |
| 확인할 출력 | 변환/정리된 표와 원본 event/object 대응 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 테이블 encoding과 의미적 필터를 분리; threshold·경로·event/object ID lineage를 유지. |
| 다음 작업 ID | IO-05, FILTER-01, STAT-02 |
| 의미·옵션·한계 | Pandas dataframe representation 호환 자체를 제품 계산 목표로 삼지 않되 제공하던 입력/선택 기능은 보존. |

**현재 PIX 근거:** `import_log`.
소스: [src/pix/tabular/reader.py](../../../src/pix/tabular/reader.py), [src/pix/tabular/mapping.py](../../../src/pix/tabular/mapping.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/importer/csv/util.py :: succint_stream_to_exploded_stream`
- `ocpa/objects/log/importer/csv/util.py :: succint_mdl_to_exploded_mdl`
- `ocpa/objects/log/importer/csv/util.py :: clean_normalized_frequency`
- `ocpa/objects/log/importer/csv/util.py :: clean_frequency`
- `ocpa/objects/log/importer/csv/util.py :: filter_paths`
- `ocpa/objects/log/importer/csv/util.py :: clean_arc_frequency`
- `ocpa/objects/log/importer/csv/util.py :: filter_by_timestamp`
- `ocpa/objects/log/importer/csv/util.py :: filter_object_df_by_object_ids`

## OC-DATA-003

**여러 OCEL을 합치거나 실행을 표본 선택하고 참조 객체를 정리하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 복수 OCEL/JSON 또는 원본 log, 표본/참조 선택 |
| 확인할 출력 | 병합·복사·표본 sublog와 충돌·선택 이력 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | ID collision 정책·원본 provenance가 있는 merge와 재현 가능한 sampling·copy/sublog 구현. |
| 다음 작업 ID | IO-05, FILTER-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 원본 merge_json은 같은 ID를 나중 값으로 덮어쓰고 merged.json을 기록. 부작용/충돌을 기본 정답 동작으로 복제하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/util/util.py :: merge_json`
- `ocpa/objects/log/variants/table.py :: Table.sample_cases`
- `ocpa/objects/log/variants/table.py :: Table.get_objects_of_variants`
- `ocpa/objects/log/variants/table.py :: Table.remove_object_references`
- `ocpa/objects/log/util/misc.py :: remove_object_references`
- `ocpa/objects/log/util/misc.py :: copy_log`
- `ocpa/objects/log/util/misc.py :: copy_log_from_df`
- `ocpa/objects/log/util/misc.py :: get_objects_of_variants`

## OC-RULE-001

**객체형별 두 활동의 causal·concurrent·choice·skip 강도가 규칙을 만족하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ConstraintGraph CF edge, OCEL, 객체형/threshold |
| 확인할 출력 | 규칙별 충족 여부·관계 강도·분모와 witness |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | causal/concur/choice/skip의 수식·분모·객체형 및 threshold를 대응. |
| 다음 작업 ID | RULE-01, RULE-02 |
| 의미·옵션·한계 | LOG_BASED='log_based'. 현 PIX 5종 object trace rule과 aggregate relation metric은 같지 않음. 원본 factory는 필수 diag 인자를 log_based.apply에 전달하지 않는 정적 호출 불일치가 있어 registry 존재≠실행 가능. |

**현재 PIX 근거:** `evaluate_constraints`.
소스: [src/pix/compute/constraints.py](../../../src/pix/compute/constraints.py), [src/pix/contracts/constraint.py](../../../src/pix/contracts/constraint.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/constraint_monitoring/versions/log_based.py :: evaluate_cf_edge`
- 변형 `ocpa/algo/conformance/constraint_monitoring/algorithm.py :: VERSIONS` → `log_based`
  - 등록 이름 `log_based` / 상수·키 `LOG_BASED` / 대상 `log_based.apply`

## OC-RULE-002

**활동 이벤트의 객체 부재·참여·한 개·여러 개 비율이 규칙을 만족하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ConstraintGraph object edge, OCEL, 객체형/threshold |
| 확인할 출력 | Event 객체 참여 cardinality 비율 및 규칙 판정 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | absent/present/singular/multiple을 event 모집단과 객체형 cardinality로 평가. |
| 다음 작업 ID | RULE-01, RULE-02 |
| 의미·옵션·한계 | PIX CountRule은 객체 trace의 활동 발생 수 규칙으로, 이벤트당 객체 cardinality 규칙을 이미 구현한 것은 아님. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/constraint_monitoring/versions/log_based.py :: evaluate_or_edge`
- 변형 `ocpa/algo/conformance/constraint_monitoring/algorithm.py :: VERSIONS` → `log_based`
  - 등록 이름 `log_based` / 상수·키 `LOG_BASED` / 대상 `log_based.apply`

## OC-RULE-003

**모델의 진단 성능값이 지정한 비교식·threshold를 만족하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ConstraintGraph performance edge, model diagnostics |
| 확인할 출력 | 비교식 판정·측정값/threshold와 미평가 원인 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Diagnostic metric+aggregation+object type와 <,>,<=,>=,!=,= 비교를 공통 PERF 결과에 연결. |
| 다음 작업 ID | RULE-02, PERF-05 |
| 의미·옵션·한계 | 원본 <= 분기가 >=를 실행하는 정적 결함을 동일 동작 요구로 복제하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/constraint_monitoring/versions/log_based.py :: apply`
- `ocpa/algo/conformance/constraint_monitoring/versions/log_based.py :: evaluate_perf_edge`
- 변형 `ocpa/algo/conformance/constraint_monitoring/algorithm.py :: VERSIONS` → `log_based`
  - 등록 이름 `log_based` / 상수·키 `LOG_BASED` / 대상 `log_based.apply`

## OC-RULE-004

**확장 constraint graph의 OA·AA·AOA 규칙과 성능 조합을 평가하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ExtensiveConstraintGraph, OCEL, 집계/threshold |
| 확인할 출력 | OA/AA/AOA edge별 판정·수치·근거와 전체 평가 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | OA exist/absent/singular/multiple/present; agg-pooling/lagging/rediness/obj_freq/act_freq; AA agg-flow/sojourn/sync; AOA coexist/exclusive/choice/xorChoice/cause/directlyCause/precede/block 구현. |
| 다음 작업 ID | RULE-01, RULE-02, RULE-03 |
| 의미·옵션·한계 | EXTENSIVE='extensive_log_based'가 기본. Wrapper metric 문자열과 downstream registry의 연결 불일치, <= 비교 오류, 빈 모집단 0 처리는 정의/구현 결함을 구분하여 수정. |

**현재 PIX 근거:** `evaluate_constraints`.
소스: [src/pix/compute/constraints.py](../../../src/pix/compute/constraints.py), [src/pix/contracts/constraint.py](../../../src/pix/contracts/constraint.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/conformance/constraint_monitoring/versions/extensive_log_based.py :: apply`
- `ocpa/algo/conformance/constraint_monitoring/versions/extensive_log_based.py :: calculate_metric`
- `ocpa/algo/conformance/constraint_monitoring/versions/extensive_log_based.py :: compare`
- `ocpa/algo/conformance/constraint_monitoring/versions/extensive_log_based.py :: evaluate_oa_edge`
- `ocpa/algo/conformance/constraint_monitoring/versions/extensive_log_based.py :: evaluate_aa_edge`
- `ocpa/algo/conformance/constraint_monitoring/versions/extensive_log_based.py :: evaluate_aoa_edge`
- `ocpa/algo/conformance/constraint_monitoring/algorithm.py :: apply` — facade
- 변형 `ocpa/algo/conformance/constraint_monitoring/algorithm.py :: VERSIONS` → `extensive_log_based`
  - 등록 이름 `extensive_log_based` / 상수·키 `EXTENSIVE` / 대상 `extensive_log_based.apply`

## OC-RULE-005

**활동 존재·부재·동시 존재·배타·선택·XOR를 만족하는 객체와 비율은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL object traces, 객체형과 활동 조건 |
| 확인할 출력 | 조건을 만족하는 객체 ID 집합 및 모집단 비율 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체 집합 witness와 모집단 비율을 함께 반환하는 규칙/집계 구현. |
| 다음 작업 ID | RULE-01, RULE-03, STAT-02 |
| 의미·옵션·한계 | 원본 exclusiveness/xor_choice는 Boolean ~ 사용으로 기대 논리 부정을 수행하지 않는 정적 결함. PIX NotCoexistenceRule의 존재가 전체 규칙·분모 대응을 완료하지 않음. |

**현재 PIX 근거:** `evaluate_constraints`.
소스: [src/pix/compute/constraints.py](../../../src/pix/compute/constraints.py), [src/pix/contracts/constraint.py](../../../src/pix/contracts/constraint.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.existence`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.existence_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.non_existence`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.non_existence_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.coexistence`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.coexistence_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.exclusiveness`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.exclusiveness_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.choice`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.choice_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.xor_choice`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.xor_choice_metric`

## OC-RULE-006

**객체별 followed-by·directly-followed-by·precedence·block 조건의 대상과 비율은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL object traces, 객체형·두 활동·순서 조건 |
| 확인할 출력 | 순서 조건의 객체 ID 집합과 비율·반례 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 첫 출현 기준 원본 정의와 activation별 PIX Response/Precedence 의미를 별도 profile로 구분. |
| 다음 작업 ID | RULE-01, RULE-03, OCEXEC-02 |
| 의미·옵션·한계 | trace.index를 이용하는 원본 첫 출현 비교는 모든 activation의 응답 존재를 평가하는 Declare와 다름. 비어 있는 객체 모집단의 분모도 명시. |

**현재 PIX 근거:** `evaluate_constraints`.
소스: [src/pix/compute/constraints.py](../../../src/pix/compute/constraints.py), [src/pix/contracts/constraint.py](../../../src/pix/contracts/constraint.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.followed_by`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.followed_by_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.directly_followed_by`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.directly_followed_by_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.precedence`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.precedence_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.block`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.block_metric`

## OC-RULE-007

**활동 이벤트의 객체 참여 cardinality와 객체형별 관계 강도는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 활동·객체형 또는 두 활동 |
| 확인할 출력 | 객체 cardinality별 이벤트 집합/비율 및 관계 강도 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Event 모집단/object 모집단, count와 ratio를 분리한 공개 집계 및 witness 구현. |
| 다음 작업 ID | STAT-01, STAT-02, RULE-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_absence`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_absence_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_singular`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_singular_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_multiple`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_multiple_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.object_presence_metric`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.causal_relation`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.concur_relation`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.choice_relation`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.absent_involvement`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.singular_involvement`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.multiple_involvement`

## OC-RULE-008

**Constraint graph 구조를 데이터에서 만들고 규칙 근거로 연결할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 규칙 node/edge·formula를 담은 구조화 데이터 |
| 확인할 출력 | Constraint graph 모델과 계산·시각화용 ID 관계 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Activity/ObjectType/Formula node와 CF/OR/Performance 및 OA/AA/AOA edge의 명시 계약 구현. |
| 다음 작업 ID | RULE-01, MODEL-01, VIEW-02 |
| 의미·옵션·한계 | PIX trace 규칙 dataclass만으로 graph 모델을 이미 지원한다고 판단하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/retrieval/constraint_graph/algorithm.py :: apply`
- `ocpa/objects/graph/constraint_graph/obj.py :: ConstraintGraph`
- `ocpa/objects/graph/constraint_graph/obj.py :: ActivityNode`
- `ocpa/objects/graph/constraint_graph/obj.py :: ObjectTypeNode`
- `ocpa/objects/graph/constraint_graph/obj.py :: FormulaNode`
- `ocpa/objects/graph/constraint_graph/obj.py :: ControlFlowEdge`
- `ocpa/objects/graph/constraint_graph/obj.py :: ObjectRelationEdge`
- `ocpa/objects/graph/constraint_graph/obj.py :: PerformanceEdge`
- `ocpa/objects/graph/extensive_constraint_graph/obj.py :: ExtensiveConstraintGraph`
- `ocpa/objects/graph/extensive_constraint_graph/obj.py :: OAEdge`
- `ocpa/objects/graph/extensive_constraint_graph/obj.py :: AAEdge`
- `ocpa/objects/graph/extensive_constraint_graph/obj.py :: AOAEdge`

## OC-REL-001

**특정 E2O qualifier로 참여한 객체 속성이 허용 조건에 맞는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL2, activity/object type/E2O qualifier/속성 조건 |
| 확인할 출력 | 허용·비허용 참여 수, 객체/event/속성 조회 근거 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | E2O role+activity+object type+속성 조건의 witness/count를 계산; last stored row와 event-time as-of를 구분. |
| 다음 작업 ID | REL-01, REL-02, REL-03 |
| 의미·옵션·한계 | PIX는 qualifier와 속성 이력을 보존하지만 이 conformance 계산은 없음. 원본 find_last_appearance_value는 마지막 저장 행이며 as-of가 아니다. 계산과 pie chart 저장 분리. |

**현재 PIX 근거:** `import_ocel`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/ocel2_use_cases/e2o_qualifier_conformance.py :: e2o_qualifier_conformance`
- `ocpa/algo/ocel2_use_cases/e2o_qualifier_conformance.py :: find_last_appearance_value`

## OC-REL-002

**이벤트에 참여한 source×target 객체 쌍의 O2O qualifier가 허용 관계인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL2, activity/source·target 객체형, O2O qualifier |
| 확인할 출력 | 관계별 허용·비허용/부재 객체쌍 occurrence 수 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 관계 방향·qualifier·부재·event별 쌍 occurrence의 분모와 진단 구현. |
| 다음 작업 ID | REL-01, REL-03 |
| 의미·옵션·한계 | PIX O2O 저장·조회와 조건 평가 계산은 별개. 고유 O2O 수와 이벤트마다 반복 집계되는 객체쌍 수를 구분. |

**현재 PIX 근거:** `import_ocel`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/ocel2_use_cases/o2o_qualifier_conformance.py :: check_o2o_qualifier_conformance`

## OC-REL-003

**객체 속성 변화의 시간 순서와 이벤트 시점 값을 확인할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL2 object change table, 객체 ID·속성 |
| 확인할 출력 | 객체 속성 시계열 그림과 시점별 값의 근거 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체 속성 시계열 view와 as-of query를 연결; 동일시각 충돌·초기값·결측 표시. |
| 다음 작업 ID | REL-02, VIEW-01, VIEW-02 |
| 의미·옵션·한계 | 원본 공개 기능은 plot이며 일반 as-of 계산 구현으로 집계하지 않음. |

**현재 PIX 근거:** `import_ocel`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/ocel2_use_cases/object_change_tables.py :: plot_attribute_over_time`

## OC-FEAT-001

**이벤트 시점에 활동·객체·이전 행동·속성의 feature를 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, event feature spec, 관측 cutoff |
| 확인할 출력 | 14종 활동·객체·과거속성 feature 값과 근거 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 14종 event feature의 관측 경계·vocabulary·결측·원본 근거 및 결과 저장 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | EVENT_BASED="event_based". 로그의 보존 데이터나 trace 계산 재료를 feature extractor 완료로 세지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: number_of_objects`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: event_activity`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: event_identity`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: event_type_count`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: preceding_activities`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: previous_activity_count`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: current_activities`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: agg_previous_char_values`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: preceding_char_values`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: characteristic_value`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: current_total_object_count`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: previous_object_count`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: previous_type_count`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: event_objects`
- 변형 `ocpa/algo/predictive_monitoring/factory.py :: VERSIONS[EVENT_BASED]` → `num_objects`, `event_activity`, `event_identity`, `event_type_count`, `event_preceding_activities`, `event_previous_activity_count`, `event_current_activities`, `event_aggregate_previous_char`, `event_preceding_char_values`, `event_char_value`, `event_current_total_object_count`, `event_previous_object_count`, `event_previous_type_count`, `event_objects`
  - 등록 이름 `num_objects` / 상수·키 `'num_objects'` / 대상 ``
  - 등록 이름 `event_activity` / 상수·키 `'event_activity'` / 대상 ``
  - 등록 이름 `event_identity` / 상수·키 `'event_identity'` / 대상 ``
  - 등록 이름 `event_type_count` / 상수·키 `'event_type_count'` / 대상 ``
  - 등록 이름 `event_preceding_activities` / 상수·키 `'event_preceding_activities'` / 대상 ``
  - 등록 이름 `event_previous_activity_count` / 상수·키 `'event_previous_activity_count'` / 대상 ``
  - 등록 이름 `event_current_activities` / 상수·키 `'event_current_activities'` / 대상 ``
  - 등록 이름 `event_aggregate_previous_char` / 상수·키 `'event_aggregate_previous_char'` / 대상 ``
  - 등록 이름 `event_preceding_char_values` / 상수·키 `'event_preceding_char_values'` / 대상 ``
  - 등록 이름 `event_char_value` / 상수·키 `'event_char_value'` / 대상 ``
  - 등록 이름 `event_current_total_object_count` / 상수·키 `'event_current_total_object_count'` / 대상 ``
  - 등록 이름 `event_previous_object_count` / 상수·키 `'event_previous_object_count'` / 대상 ``
  - 등록 이름 `event_previous_type_count` / 상수·키 `'event_previous_type_count'` / 대상 ``
  - 등록 이름 `event_objects` / 상수·키 `'event_objects'` / 대상 ``

## OC-FEAT-002

**Service·실행 기간·elapsed·remaining·synchronization 등의 event feature를 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, time feature spec, 관측 cutoff/target horizon |
| 확인할 출력 | 10종 event 시간 feature와 input/target 구분 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 10종 시간 feature의 수식·시점·현재 input과 미래 target 구분을 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02, PERF-01, PERF-02 |
| 의미·옵션·한계 | PIX 일부 temporal 계산은 있으나 feature 생성/관측 cutoff 계약은 없음. Remaining/execution duration을 온라인 input으로 쓰면 누출 가능. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: service_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: execution_duration`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: elapsed_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: remaining_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: lagging_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: pooling_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: waiting_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: sojourn_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: synchronization_time`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: flow_time`
- 변형 `ocpa/algo/predictive_monitoring/factory.py :: VERSIONS[EVENT_BASED]` → `event_service`, `event_execution_time`, `event_elapsed_time`, `event_remaining_time`, `event_lagging_time`, `event_pooling_time`, `event_waiting_time`, `event_sojourn_time`, `event_synchronization_time`, `event_flow_time`
  - 등록 이름 `event_service` / 상수·키 `'event_service'` / 대상 ``
  - 등록 이름 `event_execution_time` / 상수·키 `'event_execution_time'` / 대상 ``
  - 등록 이름 `event_elapsed_time` / 상수·키 `'event_elapsed_time'` / 대상 ``
  - 등록 이름 `event_remaining_time` / 상수·키 `'event_remaining_time'` / 대상 ``
  - 등록 이름 `event_lagging_time` / 상수·키 `'event_lagging_time'` / 대상 ``
  - 등록 이름 `event_pooling_time` / 상수·키 `'event_pooling_time'` / 대상 ``
  - 등록 이름 `event_waiting_time` / 상수·키 `'event_waiting_time'` / 대상 ``
  - 등록 이름 `event_sojourn_time` / 상수·키 `'event_sojourn_time'` / 대상 ``
  - 등록 이름 `event_synchronization_time` / 상수·키 `'event_synchronization_time'` / 대상 ``
  - 등록 이름 `event_flow_time` / 상수·키 `'event_flow_time'` / 대상 ``

## OC-FEAT-003

**현재 자원·전체 workload와 이벤트 자원 feature는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL resource/interval, workload feature spec |
| 확인할 출력 | 3종 자원·현재 workload feature |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 3종 resource/workload feature의 관측창·interval·동시성·자원 결측 정의를 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02, ORG-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: current_resource_workload`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: current_total_workload`
- `ocpa/algo/predictive_monitoring/event_based_features/extraction_functions.py :: event_resource`
- 변형 `ocpa/algo/predictive_monitoring/factory.py :: VERSIONS[EVENT_BASED]` → `event_current_resource_workload`, `event_current_total_workload`, `event_resource`
  - 등록 이름 `event_current_resource_workload` / 상수·키 `'event_current_resource_workload'` / 대상 ``
  - 등록 이름 `event_current_total_workload` / 상수·키 `'event_current_total_workload'` / 대상 ``
  - 등록 이름 `event_resource` / 상수·키 `'event_resource'` / 대상 ``

## OC-FEAT-004

**실행별 크기·경계·기간·객체·활동·서비스 feature는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL execution, feature spec, 관측 완결성 |
| 확인할 출력 | 10종 execution 크기·기간·경계·서비스 feature |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 10종 execution feature와 열린 실행의 관측 완결성, 집계 근거 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02, PERF-04 |
| 의미·옵션·한계 | EXECUTION_BASED="execution_based". exec_identity의 상수 1은 집계 identity feature이며 미구현 placeholder가 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: number_of_events`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: number_of_ending_events`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: throughput_time`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: execution`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: number_of_objects`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: unique_activities`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: number_of_starting_events`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: delta_last_event`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: service_time`
- `ocpa/algo/predictive_monitoring/execution_based_features/extraction_functions.py :: avg_service_time`
- 변형 `ocpa/algo/predictive_monitoring/factory.py :: VERSIONS[EXECUTION_BASED]` → `num_events`, `num_end_events`, `exec_throughput`, `exec_identity`, `exec_objects`, `exec_uniq_activities`, `exec_num_start_events`, `exec_last_event`, `exec_service_time`, `exec_avg_service_time`
  - 등록 이름 `num_events` / 상수·키 `'num_events'` / 대상 ``
  - 등록 이름 `num_end_events` / 상수·키 `'num_end_events'` / 대상 ``
  - 등록 이름 `exec_throughput` / 상수·키 `'exec_throughput'` / 대상 ``
  - 등록 이름 `exec_identity` / 상수·키 `'exec_identity'` / 대상 ``
  - 등록 이름 `exec_objects` / 상수·키 `'exec_objects'` / 대상 ``
  - 등록 이름 `exec_uniq_activities` / 상수·키 `'exec_uniq_activities'` / 대상 ``
  - 등록 이름 `exec_num_start_events` / 상수·키 `'exec_num_start_events'` / 대상 ``
  - 등록 이름 `exec_last_event` / 상수·키 `'exec_last_event'` / 대상 ``
  - 등록 이름 `exec_service_time` / 상수·키 `'exec_service_time'` / 대상 ``
  - 등록 이름 `exec_avg_service_time` / 상수·키 `'exec_avg_service_time'` / 대상 ``

## OC-FEAT-005

**Event/execution feature를 graph로 저장하고 train/test 변환을 fit할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, feature spec, scaler/encoder, split 비율 |
| 확인할 출력 | Feature storage/graph와 train-fit 변환·train/validation/test |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Feature graph·node/edge attrs·storage, cutoff/target와 그룹 독립 split, train-only fit/normalization 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | 원본 split은 execution ID random split+train fit이나 공유 객체 누출까지 막지 않음. exec_feature는 선언만 있고 미등록. object-attribute feature params는 미래 기능 명시이므로 완성 계산에 포함하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/factory.py :: apply`
- `ocpa/algo/predictive_monitoring/obj.py :: Feature_Storage`
- `ocpa/algo/predictive_monitoring/obj.py :: Feature_Storage.Feature_Graph`
- `ocpa/algo/predictive_monitoring/obj.py :: Feature_Storage.add_feature_graph`
- `ocpa/algo/predictive_monitoring/obj.py :: Feature_Storage.extract_normalized_train_test_split`
- 변형 `ocpa/algo/predictive_monitoring/factory.py :: VERSIONS` → `event_based`, `execution_based`
  - 등록 이름 `event_based` / 상수·키 `EVENT_BASED` / 대상 `{EVENT_NUM_OF_OBJECTS: event_features.number_of_objects, EVENT_ACTIVITY: event_features.event_activity, EVENT_SERVICE_TIME: event_features.service_time, EVENT_IDENTITY: event_features.event_identity, EVENT_TYPE_COUNT: event_features.event_type_count, EVENT_PRECEDING_ACTIVITIES: event_features.preceding_activities, EVENT_PREVIOUS_ACTIVITY_COUNT: event_features.previous_activity_count, EVENT_CURRENT_ACTIVITIES: event_features.current_activities, EVENT_AGG_PREVIOUS_CHAR_VALUES: event_features.agg_previous_char_values, EVENT_PRECEDING_CHAR_VALUES: event_features.preceding_char_values, EVENT_CHAR_VALUE: event_features.characteristic_value, EVENT_CURRENT_RESOURCE_WORKLOAD: event_features.current_resource_workload, EVENT_CURRENT_TOTAL_WORKLOAD: event_features.current_total_workload, EVENT_RESOURCE: event_features.event_resource, EVENT_CURRENT_TOTAL_OBJECT_COUNT: event_features.current_total_object_count, EVENT_PREVIOUS_OBJECT_COUNT: event_features.previous_object_count, EVENT_PREVIOUS_TYPE_COUNT: event_features.previous_type_count, EVENT_OBJECTS: event_features.event_objects, EVENT_EXECUTION_DURATION: event_features.execution_duration, EVENT_ELAPSED_TIME: event_features.elapsed_time, EVENT_REMAINING_TIME: event_features.remaining_time, EVENT_LAGGING_TIME: event_features.lagging_time, EVENT_POOLING_TIME: event_features.pooling_time, EVENT_WAITING_TIME: event_features.waiting_time, EVENT_SOJOURN_TIME: event_features.sojourn_time, EVENT_SYNCHRONIZATION_TIME: event_features.synchronization_time, EVENT_FLOW_TIME: event_features.flow_time}`
  - 등록 이름 `execution_based` / 상수·키 `EXECUTION_BASED` / 대상 `{EXECUTION_NUM_OF_EVENTS: execution_features.number_of_events, EXECUTION_NUM_OF_END_EVENTS: execution_features.number_of_ending_events, EXECUTION_THROUGHPUT: execution_features.throughput_time, EXECUTION_IDENTITY: execution_features.execution, EXECUTION_NUM_OBJECT: execution_features.number_of_objects, EXECUTION_UNIQUE_ACTIVITIES: execution_features.unique_activities, EXECUTION_NUM_OF_STARTING_EVENTS: execution_features.number_of_starting_events, EXECUTION_LAST_EVENT_TIME_BEFORE: execution_features.delta_last_event, EXECUTION_SERVICE_TIME: execution_features.service_time, EXECUTION_AVG_SERVICE_TIME: execution_features.avg_service_time}`

## OC-FEAT-006

**Feature graph를 event 행의 표로 인코딩하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Feature storage, 선택 graph/event index |
| 확인할 출력 | Event 행×feature 열 테이블 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Feature 열 순서·mask·ID·집계 대상/관측 cutoff를 유지한 table encoding 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/tabular.py :: construct_table`

## OC-FEAT-007

**Feature를 sequence와 길이 k 학습 표본/target으로 만드는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Feature storage/sequence, k·feature·target 선택 |
| 확인할 출력 | Event feature sequence 및 길이 k 학습 표본·target |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체별 순서·event ID·padding·target horizon·분할과 sliding k 표본 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | 원본 construct_sequence는 event ID 정렬. ID 정렬을 발생 시각이나 인과 순서로 오인하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/sequential.py :: construct_sequence`
- `ocpa/algo/predictive_monitoring/sequential.py :: construct_k_dataset`

## OC-FEAT-008

**시간창별 event/execution feature를 집계한 시계열을 만드는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 시간창 w, event/case feature·포함 전략 |
| 확인할 출력 | 시간창별 집계 feature 시계열 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 창 길이/경계·실행 포함 전략·빈 창·0과 결측의 구분, 검산 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02, PERF-04 |
| 의미·옵션·한계 | 원본 truthiness filter는 0 feature도 제외한다. 0 제외를 자동 정답으로 복제하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/predictive_monitoring/time_series.py :: construct_time_series`

## OC-FEAT-009

**Feature 표준화·선형 회귀·MAE 계산을 제공하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 수치 행렬 X·y 또는 예측/실제값 |
| 확인할 출력 | 표준화 값/역변환·회귀 계수/예측·MAE |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 일반 수치 연산의 native/선택 backend 역할, 0분산·특이행렬·held-out 평가 범위를 정의하고 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02, SCOPE-04 |
| 의미·옵션·한계 | OCPA 자체 util에도 간단한 학습/평가 계산이 있음. Process intelligence 알고리즘과 일반 numeric support를 구분하여 유지; Schumpeter LLM 학습으로 범위 확대하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/util/util.py :: StandardScaler`
- `ocpa/util/util.py :: StandardScaler.fit`
- `ocpa/util/util.py :: StandardScaler.transform`
- `ocpa/util/util.py :: StandardScaler.fit_transform`
- `ocpa/util/util.py :: StandardScaler.inverse_transform`
- `ocpa/util/util.py :: LinearRegression`
- `ocpa/util/util.py :: LinearRegression.fit`
- `ocpa/util/util.py :: LinearRegression.predict`
- `ocpa/util/util.py :: mean_absolute_error`

## OC-ACT-001

**Constraint interval pattern에 맞는 action 후보를 찾는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Constraint instances, temporal pattern/action graph |
| 확인할 출력 | Pattern match 근거와 action 후보·기간 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Pattern mapping·시간 관계·후보와 근거 생성; no-op 비교, mapping 부재·관측 부족 상태 구현. |
| 다음 작업 ID | ACT-01, RULE-02 |
| 의미·옵션·한계 | TEMPORAL_PATTERN_BASED='temporal_pattern_based'. Main은 before/equal/overlaps/during만 사용; complete_allens_relation의 meets/starts/finishes가 있어도 Allen 13종 전체 지원은 아님. 원본은 첫 valid mapping과 action별 최장 duration을 선택. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: apply`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: latest_end_date`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: generate_all_possible_mappings`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: complete_allens_relation`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: allens_relation`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: merge`
- `ocpa/algo/util/aopm/action_engine/algorithm.py :: apply` — facade
- 변형 `ocpa/algo/util/aopm/action_engine/algorithm.py :: VERSIONS` → `temporal_pattern_based`
  - 등록 이름 `temporal_pattern_based` / 상수·키 `TEMPORAL_PATTERN_BASED` / 대상 `temporal_pattern_based.apply`

## OC-ACT-002

**후보 action들의 선행·충돌 조건을 지키는 일정과 waiting/flow/makespan은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Action 후보, precedence/conflict, 시간 단위 |
| 확인할 출력 | 가능 일정·action instance, makespan/waiting/flow와 제외 사유 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Cycle/불가능/무진행 검출, 명시 시간 단위, 가능 일정과 목적함수·한도에 따른 최적성 범위 구현. |
| 다음 작업 ID | ACT-02, QA-03 |
| 의미·옵션·한계 | OCPA scheduler는 greedy 시간 단위 계획이며 전역 최적화 보장이 아님. Factory action_conflicts 인자를 구현은 precedence_relations로 해석. 실제 행동 실행은 Schumpeter 범위. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: create_action_conflict`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: instantiate_action_conflict`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: complete`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: plan_actions`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: compute_total_waiting_time`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: compute_total_flow_time`
- `ocpa/algo/util/aopm/action_engine/versions/temporal_pattern_based.py :: enhance_to_absolute_time`

## OC-ACT-003

**Action이 구조상 전후 활동과 객체형에 미치는 영향 범위는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ActionChange, OCPN/action interface |
| 확인할 출력 | 활동·객체형별 직접/선행/후행 구조 영향 집합·수량 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | SA.Function.Prior/Posterior와 SA.Object.Direct/Prior/Posterior 집합·count와 근거를 native 계산. |
| 다음 작업 ID | ACT-03, MODEL-06 |
| 의미·옵션·한계 | AIM_BASED='action_interface_model_based'. Factory annotation ActionInstance와 실제 ActionChange 요구는 다름. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: apply`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: type_specific_FSA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: backward_pass_FSA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: forward_pass_FSA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: direct_OSA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: backward_pass_OSA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: forward_pass_OSA`
- `ocpa/objects/aopm/impact/obj.py :: ActionChange`
- `ocpa/objects/aopm/impact/obj.py :: FunctionWiseStructuralImpact.quantify`
- `ocpa/objects/aopm/impact/obj.py :: ObjectWiseStructuralImpact.quantify`
- `ocpa/algo/util/aopm/impact_analysis/algorithm.py :: apply` — facade
- 변형 `ocpa/algo/util/aopm/impact_analysis/algorithm.py :: VERSIONS` → `action_interface_model_based`
  - 등록 이름 `action_interface_model_based` / 상수·키 `AIM_BASED` / 대상 `action_interface_model_based.apply`

## OC-ACT-004

**Action 시점의 marking과 관련 subnet에 어떤 객체가 영향을 받는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ActionChange, OCEL·OCPN, 관측 시점 marking |
| 확인할 출력 | 관련 subnet의 전후 영향 객체 집합·수량 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Marking 산출·관련 객체 집합·운영 영향 전후 구간, 계산 불가 원인/witness 구현. |
| 다음 작업 ID | ACT-03, OCONF-02, MODEL-06 |
| 의미·옵션·한계 | PIX 모델 marking 표현만으로 로그 시점 marking/영향 분석을 구현했다고 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: backward_pass_OIA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: forward_pass_OIA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: compute_marking`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: new_compute_marking`
- `ocpa/objects/aopm/impact/obj.py :: OperationalImpact.quantify`

## OC-ACT-005

**Action 전후 관측창에서 활동·객체 성능이 얼마나 달라졌는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | ActionChange의 관측창·비교창, OCEL, measure/aggregation |
| 확인할 출력 | FPA/OPA 성능 차이·부호/모집단·결측 원인 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Cohort/분모/시간창/변화 부호·결측 이유를 명시한 성능 차이 계산. |
| 다음 작업 ID | ACT-03, PERF-02, PERF-04 |
| 의미·옵션·한계 | 원본 FPA=comp−change, OPA=change−comp. FPA measure 문자열 flow/sojourn/syncronization/pooling/lagging/rediness, OPA object_freq/elapsed/remaining; registry 오타와 모든 예외→None 처리를 정답으로 복제하지 않음. Wrapper quantify의 float에 len 사용은 정적 오류이며 main 수치 계산과 구분. 관측 차이를 인과 효과로 확정하지 않음. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: FPA`
- `ocpa/algo/util/aopm/impact_analysis/versions/action_interface_model_based.py :: OPA`
- `ocpa/objects/aopm/impact/obj.py :: FunctionWisePerformanceImpact.quantify`
- `ocpa/objects/aopm/impact/obj.py :: ObjectWisePerformanceImpact.quantify`

## OC-ACT-006

**Constraint instance와 action interface의 설정을 교환하고 변경을 계산하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Constraint instance 파일, action/interface/configuration 정의 |
| 확인할 출력 | 구조화 instance·action 계약 및 configuration 변경값 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Action/constraint 정의·설정 delta와 serializable 계약 구현. |
| 다음 작업 ID | ACT-01, ACT-02, SCOPE-03 |
| 의미·옵션·한계 | IntegrityRuleBasedAction.apply에는 configuration 변경 계산이 있음. Reaction/Derivation action은 필드만 있으므로 실행 알고리즘 완성으로 세지 않음. 외부 agent 실행 runtime은 PIX 경계 밖. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/aopm/action_interface_model/obj.py :: ActionInterfaceModel`
- `ocpa/objects/aopm/action_interface_model/obj.py :: ActionInterfaceModel.to_dict`
- `ocpa/objects/aopm/action_interface_model/obj.py :: Configuration`
- `ocpa/objects/aopm/action_interface_model/obj.py :: OperationalState`
- `ocpa/objects/aopm/action_interface_model/obj.py :: IntegrityRuleBasedAction.apply`
- `ocpa/objects/aopm/action_interface_model/obj.py :: ReactionRuleBasedAction`
- `ocpa/objects/aopm/action_interface_model/obj.py :: DerivationRuleBasedAction`
- `ocpa/objects/aopm/action_engine/importer/constraint_instance/factory.py :: apply`
- `ocpa/objects/aopm/action_engine/obj.py :: ConstraintInstance`
- `ocpa/objects/aopm/action_engine/obj.py :: ConstraintPattern`
- `ocpa/objects/aopm/action_engine/obj.py :: ActionGraph`
- `ocpa/objects/aopm/action_engine/obj.py :: ActionCandidate`
- `ocpa/objects/aopm/action_engine/obj.py :: ActionInstance`

## OC-IO-001

**기존 OCEL 1 JSON/XML 데이터를 의미를 보존해 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL1 JSON/XML 파일과 import 설정 |
| 확인할 출력 | 검증된 native OCEL 및 원본/변환 진단 |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCPA 생산자 fixture·edge metadata·별도 object attribute table 처리와 원본 보존 검증을 확대. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | OCEL_JSON='ocel_json', OCEL_XML='ocel_xml'. matched_narrow는 PIX 명시 입력 profile/검증 사례의 보존만 뜻함; OCPA의 모든 허용 비표준 입력 및 lazy analysis까지 동일함을 뜻하지 않음. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`, `import_log`.
소스: [src/pix/ocel/ingest/formats/legacy.py](../../../src/pix/ocel/ingest/formats/legacy.py), [src/pix/ocel/ingest/reader.py](../../../src/pix/ocel/ingest/reader.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/importer/ocel/factory.py :: apply`
- 변형 `ocpa/objects/log/importer/ocel/factory.py :: VERSIONS` → `ocel_json`, `ocel_xml`
  - 등록 이름 `ocel_json` / 상수·키 `OCEL_JSON` / 대상 `import_ocel_json.apply`
  - 등록 이름 `ocel_xml` / 상수·키 `OCEL_XML` / 대상 `import_ocel_xml.apply`

## OC-IO-002

**OCEL 2 XML/SQLite의 E2O/O2O qualifier와 객체 변경 이력을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL2 XML/SQLite 파일 |
| 확인할 출력 | E2O/O2O qualifier·객체 속성 이력을 보존한 native OCEL |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | 생산자별 실제 입력과 타입/관계/변경 이력 보존 사례를 확장; 소스의 import 후 자동 분석은 명시 계산으로 분리. |
| 다음 작업 ID | IO-01, IO-05, REL-01, REL-02 |
| 의미·옵션·한계 | OCEL2_SQLITE='ocel2_sqlite'. XML은 factory.apply 직접 구현이며 VERSIONS 없음. OCEL 2 import 보존이 REL 계산 완료는 아님. XML parse/process helper는 import의 타입·관계·객체 이력 추출 단계로 같은 행에 대응하며 개별 알고리즘 수를 늘리지 않는다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`, `import_log`.
소스: [src/pix/ocel/ingest/formats/sqlite.py](../../../src/pix/ocel/ingest/formats/sqlite.py), [src/pix/ocel/ingest/formats/xml.py](../../../src/pix/ocel/ingest/formats/xml.py), [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/importer/ocel2/sqlite/factory.py :: apply`
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: apply`
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: parse_xml` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_object_types` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_event_types` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_objects` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_object_children` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_target_objects` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_object_attributes` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_events` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_event_objects` — support
- `ocpa/objects/log/importer/ocel2/xml/factory.py :: process_event_attributes` — support
- 변형 `ocpa/objects/log/importer/ocel2/sqlite/factory.py :: VERSIONS` → `ocel2_sqlite`
  - 등록 이름 `ocel2_sqlite` / 상수·키 `OCEL2_SQLITE` / 대상 `import_ocel2_sqlite.apply`

## OC-IO-003

**CSV의 활동·시각·객체 열을 매핑하고 별도 객체 속성표를 입력할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | CSV, 활동·시각·객체/속성 열 매핑, 선택적 객체 속성표 |
| 확인할 출력 | 의미가 명시된 native OCEL 또는 case log와 import 진단 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | TO_DF/TO_OBJ/TO_OCEL 목적별 native 입력 매핑과 별도 object attribute table 결합·delimiter profile 검산. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | TO_DF='to_df', TO_OBJ='to_obj', TO_OCEL='to_ocel'. PIX mapping import는 있으나 OCPA DataFrame 반환/별도 속성표의 모든 결합 경로 동치는 미확정. 표현 class를 복제할 의무와 기능 대체를 구분. |

**현재 PIX 근거:** `import_log`, `CaseTableMapping`, `OCELTableMapping`.
소스: [src/pix/tabular/reader.py](../../../src/pix/tabular/reader.py), [src/pix/tabular/mapping.py](../../../src/pix/tabular/mapping.py), [src/pix/io.py](../../../src/pix/io.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/importer/csv/factory.py :: apply`
- 변형 `ocpa/objects/log/importer/csv/factory.py :: VERSIONS` → `to_df`, `to_obj`, `to_ocel`
  - 등록 이름 `to_df` / 상수·키 `TO_DF` / 대상 `to_df.apply`
  - 등록 이름 `to_obj` / 상수·키 `TO_OBJ` / 대상 `to_obj.apply`
  - 등록 이름 `to_ocel` / 상수·키 `TO_OCEL` / 대상 `to_ocel.apply`

## OC-IO-004

**OCEL object 표현과 dataframe/CSV 표현을 서로 바꿀 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 객체 또는 dataframe, column mapping |
| 확인할 출력 | OCEL 또는 event/object dataframe 쌍과 변환 손실 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | DF_TO_OCEL 입력 의미와 JSONOCEL_TO_CSV 출력 두 표의 객체 보존·손실 보고·열 매핑 구현. |
| 다음 작업 ID | IO-04, IO-05 |
| 의미·옵션·한계 | JSONOCEL_TO_CSV='json_to_csv', DF_TO_OCEL='df_to_ocel'. 원본 apply는 dataframe 쌍 변환이지 항상 CSV 파일 저장이 아님. 미참여 객체형 누락의 원본 제한을 그대로 복제하지 않는다. |

**현재 PIX 근거:** `import_log`.
소스: [src/pix/tabular/reader.py](../../../src/pix/tabular/reader.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/converter/factory.py :: apply`
- 변형 `ocpa/objects/log/converter/factory.py :: VERSIONS` → `json_to_csv`, `df_to_ocel`
  - 등록 이름 `json_to_csv` / 상수·키 `JSONOCEL_TO_CSV` / 대상 `jsonocel_to_csv.apply`
  - 등록 이름 `df_to_ocel` / 상수·키 `DF_TO_OCEL` / 대상 `df_to_ocel.apply`

## OC-IO-005

**OCPA가 쓰는 OCEL 1 JSON 파일로 다시 출력할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Native OCEL, 출력 경로와 OCEL1 profile |
| 확인할 출력 | OCEL1 JSON 파일 또는 표현 불가/손실 보고 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCEL1 JSON output profile과 OCEL2→1 정보 손실/거절 조건을 구현. |
| 다음 작업 ID | IO-04, IO-05 |
| 의미·옵션·한계 | OCEL_JSON='ocel_json'. 현재 PIX writer는 OCEL2 JSON/XML/SQLite이며 OCEL1 JSON exporter의 완성 대체는 아님. 독립 검토: 기존 OCEL2 exporter는 선행 자산이며 OCEL1 JSON writer 구현으로 세지 않는다(PM-IO-013과 동일 상태). |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/ocel/export/writer.py](../../../src/pix/ocel/export/writer.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/exporter/ocel/factory.py :: apply`
- 변형 `ocpa/objects/log/exporter/ocel/factory.py :: VERSIONS` → `ocel_json`
  - 등록 이름 `ocel_json` / 상수·키 `OCEL_JSON` / 대상 `export_ocel_json.apply`

## OC-VIEW-001

**OCPN의 제어 흐름·성능 annotation·객체 구분을 읽기 쉬운 graph로 보여주는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN, 성능 diagnostics, 표시·출력 옵션 |
| 확인할 출력 | 객체/제어흐름/성능 graph와 저장 가능한 view |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 각 OCPN view와 performance annotation의 의미적 표현을 ELK/SVG adapter로 대응하고 큰 graph 검증. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | Graphviz wrapper를 runtime에 가져오지 않음. 기존 view 기능의 의미를 제공하되 배치/모양 동치를 요구하지 않는다. 값 CONTROL_FLOW='control_flow', NEW_CONTROL_FLOW='new_control_flow', ANNOTATED_WITH_OPERA='annotated_with_opera', OCPI='ocpi'. |

**현재 PIX 근거:** `build_model_graph`, `export_html`, `render_html`.
소스: [src/pix/viewer/model_adapter.py](../../../src/pix/viewer/model_adapter.py), [src/pix/viewer/export.py](../../../src/pix/viewer/export.py), [src/pix/viewer/assets/viewer.js](../../../src/pix/viewer/assets/viewer.js).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/visualization/oc_petri_net/factory.py :: apply`
- `ocpa/visualization/oc_petri_net/factory.py :: save`
- `ocpa/visualization/oc_petri_net/factory.py :: view`
- 변형 `ocpa/visualization/oc_petri_net/factory.py :: VERSIONS` → `control_flow`, `new_control_flow`, `annotated_with_opera`, `ocpi`
  - 등록 이름 `control_flow` / 상수·키 `CONTROL_FLOW` / 대상 `control_flow.apply`
  - 등록 이름 `new_control_flow` / 상수·키 `NEW_CONTROL_FLOW` / 대상 `new_control_flow.apply`
  - 등록 이름 `annotated_with_opera` / 상수·키 `ANNOTATED_WITH_OPERA` / 대상 `annotated_with_opera.apply`
  - 등록 이름 `ocpi` / 상수·키 `OCPI` / 대상 `ocpi.apply`

## OC-VIEW-002

**Constraint graph의 활동·객체·수식·규칙 edge를 시각화하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Constraint graph와 선택적 평가 결과 |
| 확인할 출력 | 규칙 graph 표시 데이터와 근거 연결 |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Constraint graph adapter와 평가 결과/witness·unknown 범위 표시. |
| 다음 작업 ID | VIEW-01, VIEW-02, RULE-01 |
| 의미·옵션·한계 | TO_CYTOSCAPE='to_cytoscape'. Cytoscape 데이터 반환의 기능을 native graph 계약으로 대응. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/visualization/constraint_graph/algorithm.py :: apply`
- 변형 `ocpa/visualization/constraint_graph/algorithm.py :: VERSIONS` → `to_cytoscape`
  - 등록 이름 `to_cytoscape` / 상수·키 `TO_CYTOSCAPE` / 대상 `to_cytoscape.apply`

## OC-VIEW-003

**객체별 variant 실행을 chevron sequence 등으로 탐색할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Variant graph·객체 참여·표시 옵션 |
| 확인할 출력 | 객체별 순서를 보존하는 chevron/variant layout |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체 참여/순서를 보존하는 execution/variant view·drilldown 구현. |
| 다음 작업 ID | VIEW-02, VIEW-03, OCEXEC-03 |
| 의미·옵션·한계 | CHEVRON_SEQUENCES='chevron_sequences'. 스타일 복제가 아니라 실행 의미의 해석 가능성을 검토. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/visualization/log/variants/factory.py :: apply`
- 변형 `ocpa/visualization/log/variants/factory.py :: VERSIONS` → `chevron_sequences`
  - 등록 이름 `chevron_sequences` / 상수·키 `CHEVRON_SEQUENCES` / 대상 `chevron_sequences.apply`

## OC-VIEW-004

**Joint alignment의 log/model/synchronous move와 객체 참여를 시각적으로 따라갈 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Joint alignment move와 객체·모델 ID |
| 확인할 출력 | Move/객체별 alignment view와 원본 근거 연결 |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Move/객체별 순서 view와 trace/model 원본 노드 연결, 부분 탐색 상태 표시. |
| 다음 작업 ID | VIEW-01, VIEW-02, OCONF-04 |
| 의미·옵션·한계 | PIX 결과 witness/HTML report는 있으나 OCPA alignment 그림과 같은 이동별 graph 표시 전체는 미구현. |

**현재 PIX 근거:** `align_object_log`, `export_html_report`.
소스: [src/pix/compute/object_conformance.py](../../../src/pix/compute/object_conformance.py), [src/pix/viewer/export.py](../../../src/pix/viewer/export.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/visualization/alignment_viz/visualization.py :: alignment_viz`

## OC-DATA-004

**이벤트-객체 조회와 특정 활동을 포함하거나 잇는 객체 수를 계산하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL index, event/activity/object type 질의 |
| 확인할 출력 | 관련 객체 ID 및 조건별 객체/event count |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 조회·수량과 객체/event population 집계를 공개 계약으로 분리 구현. |
| 다음 작업 ID | STAT-01, STAT-02, REL-01 |
| 의미·옵션·한계 | OCEL lookup/index 기반은 있으나 원본 공개 query/count 메서드군 전체 대응은 미완료. |

**현재 PIX 근거:** `ComputationContext`, `reconstruct_traces`.
소스: [src/pix/compute/context.py](../../../src/pix/compute/context.py), [src/pix/ocel/model.py](../../../src/pix/ocel/model.py), [src/pix/compute/trace.py](../../../src/pix/compute/trace.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `ocpa 1.3.4` 공식 wheel. 함수·변형은 다음과 같다.

- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.eve_ot_objects`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.ot_objects_of_an_event`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.num_ot_objects_containing_acts`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.num_ot_objects_containing_act1_followed_by_act2`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.num_events_relating_one_ot`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.num_events_relating_no_ot`
- `ocpa/objects/log/variants/obj.py :: ObjectCentricEventLog.num_events_relating_multiple_ot`
