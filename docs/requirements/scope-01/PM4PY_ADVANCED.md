# SCOPE-01 세부 대체표 — PM4Py 고급 분석·조직·simulation·streaming·연결·시각화

기준일: **2026-09-14**. [전체 범례·증거·판정 경계](../2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md).
입력·출력은 대체할 기능을 검토하기 위한 계약이다. **현재 PIX가 이미 그 결과를 반환한다는 뜻은 아니다.** 현재 지원은 각 행의 구현·의미·소스·증거로 구분한다.
참조 경로와 symbol은 공식 배포 wheel의 위치다. wrapper·helper·backend는 추적을 위해 함께 표시하며 별도 계산 알고리즘으로 중복 집계하지 않는다.

| ID | 도메인에서 판단할 질문 | PIX 구현 | 의미 대응 | 다음 작업 |
|---|---|---|---|---|
| [PM-ADV-001](#pm-adv-001) | 전체 case를 보존하면서 학습·검증 집합을 나누는가? | 대응 구현 없음 | 미구현 | FEAT-01 |
| [PM-ADV-002](#pm-adv-002) | 예측 시점까지 관측된 prefix만 추출하는가? | 대응 구현 없음 | 미구현 | FEAT-01 |
| [PM-ADV-003](#pm-adv-003) | 전체 case의 결과와 처리·대기·도착 정보를 학습 표에 붙이는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [PM-ADV-004](#pm-adv-004) | Case 하나를 활동·속성·시간 등의 수치 feature 벡터로 표현하는가? | 대응 구현 없음 | 미구현 | FEAT-02 |
| [PM-ADV-005](#pm-adv-005) | Case 안의 각 이벤트를 순서가 유지된 feature 벡터로 표현하는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [PM-ADV-006](#pm-adv-006) | 시간 구간별 프로세스 feature와 변화 시계열을 만드는가? | 대응 구현 없음 | 미구현 | FEAT-02, FEAT-04 |
| [PM-ADV-007](#pm-adv-007) | 활동 토큰과 n-gram을 count·binary·TF-IDF 형태로 인코딩하는가? | 대응 구현 없음 | 미구현 | FEAT-02 |
| [PM-ADV-008](#pm-adv-008) | Trace를 학습된 Word2Vec·Doc2Vec 벡터로 표현하는가? | 대응 구현 없음 | 미구현 | FEAT-02, SCOPE-01 |
| [PM-ADV-009](#pm-adv-009) | Case·event 문맥을 transformer embedding으로 표현하는가? | 대응 구현 없음 | 미구현 | FEAT-02, SCOPE-01 |
| [PM-ADV-010](#pm-adv-010) | Alignment와 token replay 진단을 학습 feature로 바꾸는가? | 대응 구현 없음 | 미구현 | FEAT-02 |
| [PM-ADV-011](#pm-adv-011) | 관측 prefix 다음 활동을 target으로 생성하는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [PM-ADV-012](#pm-adv-012) | 다음 이벤트까지 시간과 완료까지 남은 시간을 target으로 생성하는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02 |
| [PM-ADV-013](#pm-adv-013) | 분기 직전 어떤 데이터가 경로 선택과 연관되는지 설명하는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-03 |
| [PM-ADV-014](#pm-adv-014) | Case feature profile로 유사한 사례를 군집화하는가? | 대응 구현 없음 | 미구현 | FEAT-02, FEAT-03 |
| [PM-ADV-015](#pm-adv-015) | Trace 속성별 하위 로그를 행동 거리로 군집화하는가? | 대응 구현 없음 | 미구현 | FEAT-03 |
| [PM-ADV-016](#pm-adv-016) | 시간에 따라 프로세스 관계 분포가 바뀌는 구간을 찾는가? | 대응 구현 없음 | 미구현 | FEAT-04 |
| [PM-ADV-017](#pm-adv-017) | 두 로그·모델의 확률적 trace 언어가 얼마나 다른가? | 대응 구현 없음 | 미구현 | FEAT-04 |
| [PM-ADV-018](#pm-adv-018) | 질문 문장과 가장 유사한 case·event를 embedding으로 선택하는가? | 대응 구현 없음 | 미구현 | FEAT-02, SCOPE-01 |
| [PM-ORG-001](#pm-org-001) | 누가 누구에게 업무를 인계하는가? | 대응 구현 없음 | 미구현 | ORG-01 |
| [PM-ORG-002](#pm-org-002) | 같은 case에서 어떤 자원들이 함께 일하는가? | 대응 구현 없음 | 미구현 | ORG-01 |
| [PM-ORG-003](#pm-org-003) | 업무를 맡겼다가 돌아오는 subcontracting 관계는 무엇인가? | 대응 구현 없음 | 미구현 | ORG-01 |
| [PM-ORG-004](#pm-org-004) | 활동 구성을 기준으로 어떤 자원이 유사한가? | 대응 구현 없음 | 미구현 | ORG-02 |
| [PM-ORG-005](#pm-org-005) | 활동 집합을 수행하는 조직 역할을 발견하는가? | 대응 구현 없음 | 미구현 | ORG-02 |
| [PM-ORG-006](#pm-org-006) | 선택한 속성의 인계 network 빈도·시간을 분석하는가? | 대응 구현 없음 | 미구현 | ORG-01 |
| [PM-ORG-007](#pm-org-007) | 발견한 조직 집단의 focus·stake·coverage·기여를 진단하는가? | 대응 구현 없음 | 미구현 | ORG-01, ORG-02 |
| [PM-ORG-008](#pm-org-008) | 자원별 활동 종류·빈도·완료 case와 기여 비율은 얼마인가? | 대응 구현 없음 | 미구현 | ORG-02 |
| [PM-ORG-009](#pm-org-009) | 자원의 평균 workload와 multitasking 정도는 얼마인가? | 대응 구현 없음 | 미구현 | ORG-03 |
| [PM-ORG-010](#pm-org-010) | 자원이 수행한 활동·case의 평균 소요시간은 얼마인가? | 대응 구현 없음 | 미구현 | ORG-03 |
| [PM-ORG-011](#pm-org-011) | 자원 간 공동 참여와 사회적 위치를 수치화하는가? | 대응 구현 없음 | 미구현 | ORG-01, ORG-02 |
| [PM-SIM-001](#pm-sim-001) | Petri net이 허용하는 유한 실행을 생성·열거하는가? | 대응 구현 없음 | 미구현 | SIM-01 |
| [PM-SIM-002](#pm-sim-002) | 확률과 시간 분포를 가진 Petri net 실행을 생성하는가? | 대응 구현 없음 | 미구현 | SIM-02 |
| [PM-SIM-003](#pm-sim-003) | Process tree로부터 무작위·전체·top-bottom 실행을 생성하는가? | 대응 구현 없음 | 미구현 | SIM-01, SIM-02 |
| [PM-SIM-004](#pm-sim-004) | DFG의 시작·끝·전이 빈도로 실행을 생성하는가? | 대응 구현 없음 | 미구현 | SIM-01 |
| [PM-SIM-005](#pm-sim-005) | DFG 경로에 성능 시간을 붙여 실행을 생성하는가? | 대응 구현 없음 | 미구현 | SIM-02 |
| [PM-SIM-006](#pm-sim-006) | Declare 규칙을 만족하는 유한 trace를 생성하는가? | 대응 구현 없음 | 미구현 | SIM-01 |
| [PM-SIM-007](#pm-sim-007) | Object-centric Petri net의 실제 객체 binding 실행을 생성하는가? | 대응 구현 없음 | 미구현 | SIM-01 |
| [PM-SIM-008](#pm-sim-008) | Object-centric causal net의 객체 binding 실행을 생성하는가? | 대응 구현 없음 | 미구현 | SIM-01, SCOPE-01 |
| [PM-SIM-009](#pm-sim-009) | 자원 제약과 queue 아래에서 처리·대기 결과를 simulation하는가? | 대응 구현 없음 | 미구현 | SIM-02, SIM-03 |
| [PM-SIM-010](#pm-sim-010) | 설정한 크기와 operator 비율의 인공 process tree를 생성하는가? | 대응 구현 없음 | 미구현 | SIM-04 |
| [PM-STREAM-001](#pm-stream-001) | 도착하는 이벤트·trace를 등록한 계산기에 전달하는가? | 대응 구현 없음 | 미구현 | STREAM-01 |
| [PM-STREAM-002](#pm-stream-002) | XES·CSV를 이벤트·trace 단위 iterator로 공급하는가? | 대응 구현 없음 | 미구현 | STREAM-01 |
| [PM-STREAM-003](#pm-stream-003) | Dataframe·OCEL 이벤트를 분석별 stream으로 나누어 공급하는가? | 대응 구현 없음 | 미구현 | STREAM-01 |
| [PM-STREAM-004](#pm-stream-004) | 새 이벤트가 오면 DFG 빈도와 시작·끝을 갱신하는가? | 대응 구현 없음 | 미구현 | STREAM-02, STREAM-03 |
| [PM-STREAM-005](#pm-stream-005) | Petri net token replay 상태를 이벤트마다 갱신하는가? | 대응 구현 없음 | 미구현 | STREAM-02, STREAM-03 |
| [PM-STREAM-006](#pm-stream-006) | 진행 중 실행의 temporal profile 위반을 갱신하는가? | 대응 구현 없음 | 미구현 | STREAM-02, STREAM-03 |
| [PM-STREAM-007](#pm-stream-007) | 진행 중 실행의 Declare automaton 상태를 갱신하는가? | 대응 구현 없음 | 미구현 | STREAM-02, STREAM-03 |
| [PM-STREAM-008](#pm-stream-008) | 진행 중 실행이 허용된 footprint 관계를 따르는가? | 대응 구현 없음 | 미구현 | STREAM-02, STREAM-03 |
| [PM-STREAM-009](#pm-stream-009) | 제한된 기억과 look-ahead로 online alignment를 근사하는가? | 대응 구현 없음 | 미구현 | STREAM-02, STREAM-03 |
| [PM-STREAM-010](#pm-stream-010) | 온라인 계산 상태를 안전하게 저장하고 재시작하는가? | 대응 구현 없음 | 미구현 | STREAM-01, STREAM-03 |
| [PM-ADV-019](#pm-adv-019) | 제어흐름 variant 빈도를 privacy 정의에 따라 익명화하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-ADV-020](#pm-adv-020) | 익명화한 제어흐름에 timestamp·속성을 privacy 정의 아래 결합하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-001](#pm-edge-001) | 외부 LLM 서비스에 분석 질문을 전달하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-002](#pm-edge-002) | 로그·모델·지표를 사람이 읽거나 LLM에 제공할 텍스트로 표현하는가? | 대응 구현 없음 | 미구현 | VIEW-01, SCOPE-01 |
| [PM-EDGE-003](#pm-edge-003) | LLM이 제안한 패턴으로 trace를 군집화하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-004](#pm-edge-004) | 자연어를 로그 질의·필터 SQL로 바꾸어 적용하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-005](#pm-edge-005) | 데이터 가설과 검사 질의를 LLM으로 생성하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-006](#pm-edge-006) | 프로세스 그림을 LLM으로 설명하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-007](#pm-edge-007) | Outlook 메일·캘린더를 event log 또는 OCEL로 수집하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-008](#pm-edge-008) | Windows 이벤트와 Chrome·Firefox 방문 기록을 로그로 수집하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-009](#pm-edge-009) | GitHub 이슈·활동을 로그로 수집하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-010](#pm-edge-010) | Camunda·SAP O2C·SAP 회계 데이터를 로그로 수집하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-011](#pm-edge-011) | 마우스·키 입력을 live event로 수집하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-EDGE-012](#pm-edge-012) | 명령행으로 기존 분석 API를 호출하는가? | 대응 구현 없음 | 미구현 | SCOPE-01 |
| [PM-VIEW-001](#pm-view-001) | DFG의 빈도·성능·비용을 그림으로 설명하는가? | 부분 대응 | 일부 의미 겹침 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-002](#pm-view-002) | Petri net의 구조·marking·replay/성능/alignment를 그림에 표현하는가? | 부분 대응 | 일부 의미 겹침 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-003](#pm-view-003) | OCDFG에서 객체형별 경로·분모·성능을 확인하는가? | 부분 대응 | 일부 의미 겹침 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-004](#pm-view-004) | OCPN의 객체형·cardinality·marking과 성능을 확인하는가? | 부분 대응 | 일부 의미 겹침 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-005](#pm-view-005) | Process tree operator와 빈도 annotation을 직접 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-006](#pm-view-006) | BPMN의 gateway·flow·layout을 읽고 저장하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-007](#pm-view-007) | POWL의 부분순서·operator·중첩 구조를 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-008](#pm-view-008) | Heuristics net의 dependency와 AND 관계를 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-009](#pm-view-009) | Transition system과 prefix trie를 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-010](#pm-view-010) | Alignment 단계와 footprint 비교를 표·행렬로 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-011](#pm-view-011) | 조직·자원 network의 빈도·시간을 탐색하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-012](#pm-view-012) | 시간축에서 이벤트 분포와 경로별 performance spectrum을 읽는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-013](#pm-view-013) | Case 기간·이벤트 발생·속성 분포를 그래프로 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-014](#pm-view-014) | 객체 연결·객체형 참여·interleaving을 그래프로 확인하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-015](#pm-view-015) | Decision tree와 variant별 duration을 설명하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |
| [PM-VIEW-016](#pm-view-016) | 일반 graph 구조를 표현하고 저장하는가? | 대응 구현 없음 | 미구현 | VIEW-01, VIEW-02, VIEW-03 |

## PM-ADV-001

**전체 case를 보존하면서 학습·검증 집합을 나누는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 단위 이벤트 로그와 학습 비율·분할 seed·그룹 제약. |
| 확인할 출력 | Case가 분할되지 않는 학습/검증 로그와 집합 구성 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case 단위 분할, seed, 객체 공유·시간 순서에 따른 누출 점검과 분할 근거 구현. |
| 다음 작업 ID | FEAT-01 |
| 의미·옵션·한계 | 참조 pandas 경로는 case마다 확률 배정한다. 정확한 비율 보장과 동일한 요구가 아니며 실행 seed 계약을 별도로 고정한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: split_train_test`

## PM-ADV-002

**예측 시점까지 관측된 prefix만 추출하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 로그와 prefix 길이 또는 관측 cutoff. |
| 확인할 출력 | 원본 순서를 유지하며 관측 범위에서 잘린 case별 prefix. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Prefix 길이·시점 cutoff·완료 관측·빈 prefix 정책 구현. |
| 다음 작업 ID | FEAT-01 |
| 의미·옵션·한계 | 기존 PIX case_traces의 전체 trace 추출이 예측 표본 생성 구현을 의미하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: get_prefixes_from_log`

## PM-ADV-003

**전체 case의 결과와 처리·대기·도착 정보를 학습 표에 붙이는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 완료 결과를 포함한 case 로그와 활동·시간·case 키. |
| 확인할 출력 | Case 결과·도착/완료율·service/waiting 등을 결합한 학습 표. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Outcome 및 집계 feature 스키마와 계산, 관측 feature/미래 target 구분 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | 참조 함수는 전체 case 정보로 dataframe을 보강한다. 예측 시점 feature에 그대로 사용하면 미래 누출 여부를 별도 판단해야 한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: extract_outcome_enriched_dataframe`

## PM-ADV-004

**Case 하나를 활동·속성·시간 등의 수치 feature 벡터로 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 로그와 활동·속성 선택, feature 옵션 및 학습 vocabulary. |
| 확인할 출력 | Case별 수치 feature 행렬과 열 이름·단위·결측 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Trace 기반 feature별 정의·명칭·단위·결측·열 순서·vocabulary 구현. |
| 다음 작업 ID | FEAT-02 |
| 의미·옵션·한계 | log_to_features.apply는 trace_encodings.apply로 위임하는 deprecated alias이다. 두 개의 독립 계산으로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: extract_features_dataframe`
- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- `pm4py/algo/transformation/log_to_features/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `TRACE_BASED`
- 변형 `pm4py/algo/transformation/log_to_features/algorithm.py :: Variants` → `TRACE_BASED`

## PM-ADV-005

**Case 안의 각 이벤트를 순서가 유지된 feature 벡터로 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 순서가 있는 case 이벤트와 event 속성·encoding 설정. |
| 확인할 출력 | Case별 이벤트 feature sequence와 열 이름·길이/결측 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Event 기반 수치열, 순서·길이·mask·prefix 단위 저장 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 |  log_to_features.EVENT_BASED는 trace_encodings의 deprecated alias이며 별도 계산으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `EVENT_BASED`
- 변형 `pm4py/algo/transformation/log_to_features/algorithm.py :: Variants` → `EVENT_BASED`

## PM-ADV-006

**시간 구간별 프로세스 feature와 변화 시계열을 만드는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 시간 속성이 있는 로그와 구간·집계·실행 backend 설정. |
| 확인할 출력 | 시간 구간별 process feature 표와 구간·표본 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 구간 경계·집계 모집단·결측 구간·지표별 단위 구현. |
| 다음 작업 ID | FEAT-02, FEAT-04 |
| 의미·옵션·한계 | TEMPORAL_LAZY는 Polars 실행 경로이다. 의미상 동일한 계산과 backend 최적화를 구분하며 Polars 자체 재개발을 요구하지 않는다. 같은 이름의 log_to_features 선택은 deprecated alias로만 추적한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: extract_temporal_features_dataframe`
- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `TEMPORAL`, `TEMPORAL_LAZY`
- 변형 `pm4py/algo/transformation/log_to_features/algorithm.py :: Variants` → `TEMPORAL`, `TEMPORAL_LAZY`

## PM-ADV-007

**활동 토큰과 n-gram을 count·binary·TF-IDF 형태로 인코딩하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace 활동 토큰과 n-gram·vocabulary·가중치/정규화 설정. |
| 확인할 출력 | Count·binary·TF-IDF trace 행렬과 학습한 vocabulary. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 토큰 구성·n 범위·어휘 학습·unseen 처리·정규화와 sparse 결과 계약 구현. |
| 다음 작업 ID | FEAT-02 |
| 의미·옵션·한계 | 참조는 scikit-learn vectorizer를 사용한다. 일반 수치 도구 경계와 PIX의 프로세스 인코딩 정의를 분리한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `COUNT2VEC`, `N_GRAMS`, `ONE_HOT`, `TF_IDF`

## PM-ADV-008

**Trace를 학습된 Word2Vec·Doc2Vec 벡터로 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace 토큰과 Word2Vec/Doc2Vec 모델·학습 또는 추론 설정. |
| 확인할 출력 | Trace별 embedding 벡터와 사용 모델·집계 설정. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 프로세스 tokenization·집계·모델 식별·seed·학습/추론 분리와 의존성 경계 결정. |
| 다음 작업 ID | FEAT-02, SCOPE-01 |
| 의미·옵션·한계 | 참조는 gensim 계산을 사용한다. 일반 embedding 학습기 자체를 PIX에 재개발하기로 확정한 것은 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `WORD2VEC`, `DOC2VEC`

## PM-ADV-009

**Case·event 문맥을 transformer embedding으로 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case/event 텍스트 표현과 transformer 모델·embedding 설정. |
| 확인할 출력 | 표본별 embedding 벡터와 표본 ID·모델 식별 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 프로세스 텍스트화·표본/관측 경계·모델 및 embedding 계약을 정의하고 제공 계층을 결정. |
| 다음 작업 ID | FEAT-02, SCOPE-01 |
| 의미·옵션·한계 | to_embeddings는 deprecated alias이다. 외부/로컬 모델 추론과 PIX 계산 엔진의 경계는 미정이며 새 foundation model 개발을 의미하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- `pm4py/algo/transformation/to_embeddings/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `BERT`, `CASES_TRANSFORMERS`, `EVENTS_TRANSFORMERS`
- 변형 `pm4py/algo/transformation/to_embeddings/algorithm.py :: Variants` → `CASES_TRANSFORMERS`, `EVENTS_TRANSFORMERS`

## PM-ADV-010

**Alignment와 token replay 진단을 학습 feature로 바꾸는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그와 Petri net 또는 모델 발견 설정, replay/alignment 옵션. |
| 확인할 출력 | Case별 alignment/token 진단 feature 행렬과 모델·열 mapping. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Transition/이동/토큰 진단의 고정 열 mapping, 불완전 탐색 mask와 모델 판본 기록 구현. |
| 다음 작업 ID | FEAT-02 |
| 의미·옵션·한계 | PIX에 alignment와 replay가 있어도 이 encoder는 아직 없다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/trace_encodings/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `ALIGNMENTS`, `TOKEN_REPLAY`

## PM-ADV-011

**관측 prefix 다음 활동을 target으로 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 순서가 있는 case 로그와 다음 활동 label 정책. |
| 확인할 출력 | 각 관측 위치의 다음 활동 target과 class vocabulary. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 다음 활동 label과 종료/censoring·분류 vocabulary 생성 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | Target 생성이며 다음 활동을 예측하는 학습 모델 자체와 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: extract_target_vector`
- `pm4py/algo/transformation/log_to_target/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/log_to_target/algorithm.py :: Variants` → `NEXT_ACTIVITY`

## PM-ADV-012

**다음 이벤트까지 시간과 완료까지 남은 시간을 target으로 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Timestamp가 있는 case 로그와 다음 시각/잔여 시간 target 선택. |
| 확인할 출력 | 각 관측 위치의 시간 target과 단위·종료/미완료 처리 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Target 기준 시각·단위·동률/역전·미완료 관측 처리 구현. |
| 다음 작업 ID | FEAT-01, FEAT-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: extract_target_vector`
- `pm4py/algo/transformation/log_to_target/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/log_to_target/algorithm.py :: Variants` → `NEXT_TIME`, `REMAINING_TIME`

## PM-ADV-013

**분기 직전 어떤 데이터가 경로 선택과 연관되는지 설명하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·Petri net·초기/최종 marking과 관측 속성·결정 학습 설정. |
| 확인할 출력 | 분기별 학습 표·decision tree/규칙 또는 결정 조건을 붙인 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 모델 분기와 이벤트 대응, 분기 직전 feature, 결정 규칙과 held-out 평가 구현. |
| 다음 작업 ID | FEAT-01, FEAT-03 |
| 의미·옵션·한계 | Replay/alignment로 결정 label을 대응시키는 단계와 학습기를 구분하고 인과 효과로 단정하지 않는다. 추가 reference_symbols의 전처리·tree 순회·집합/병합 helper는 해당 계산 내부 경로이며 별도 알고리즘 수로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/decision_mining/algorithm.py :: apply`
- `pm4py/algo/decision_mining/algorithm.py :: create_data_petri_nets_with_decisions`
- `pm4py/algo/decision_mining/algorithm.py :: get_decision_tree`
- `pm4py/algo/decision_mining/algorithm.py :: get_decisions_table`
- `pm4py/algo/decision_mining/algorithm.py :: get_decision_points`
- `pm4py/algo/decision_mining/algorithm.py :: prepare_event_log`
- `pm4py/algo/decision_mining/algorithm.py :: prepare_attributes`
- `pm4py/algo/decision_mining/algorithm.py :: get_attributes`
- `pm4py/algo/decision_mining/algorithm.py :: encode_target`

## PM-ADV-014

**Case feature profile로 유사한 사례를 군집화하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 로그와 feature·정규화·군집 estimator 설정. |
| 확인할 출력 | 군집별 하위 로그와 case별 군집 대응·설정. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 정규화·거리·군집 설정·대표 사례 및 label 재현 계약 구현. |
| 다음 작업 ID | FEAT-02, FEAT-03 |
| 의미·옵션·한계 | 참조 일반 clustering estimator 의존성과 프로세스 feature 계산 경계를 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: cluster_log`
- `pm4py/algo/clustering/profiles/algorithm.py :: apply`
- 변형 `pm4py/algo/clustering/profiles/algorithm.py :: Variants` → `SKLEARN_PROFILES`

## PM-ADV-015

**Trace 속성별 하위 로그를 행동 거리로 군집화하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace 속성으로 구분된 로그 집단과 거리·linkage variant. |
| 확인할 출력 | 집단 간 거리와 계층적 군집 결과·구성 사례. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 하위 로그 구성·Levenshtein/vector/DFG 거리·linkage·동률·빈 집합 계약과 검산 구현. |
| 다음 작업 ID | FEAT-03 |
| 의미·옵션·한계 |  추가 reference_symbols의 전처리·tree 순회·집합/병합 helper는 해당 계산 내부 경로이며 별도 알고리즘 수로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/clustering/trace_attribute_driven/algorithm.py :: apply`
- `pm4py/algo/clustering/trace_attribute_driven/algorithm.py :: bfs`
- 변형 `pm4py/algo/clustering/trace_attribute_driven/algorithm.py :: Variants` → `VARIANT_DMM_LEVEN`, `VARIANT_AVG_LEVEN`, `VARIANT_DMM_VEC`, `VARIANT_AVG_VEC`, `DFG`

## PM-ADV-016

**시간에 따라 프로세스 관계 분포가 바뀌는 구간을 찾는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 순서/시간이 있는 로그와 sublog·window·permutation·검정 설정. |
| 확인할 출력 | 변화 후보 지점·관련 p-value 및 구간별 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 관계 feature·sublog/window·permutation seed·검정·효과 크기·변화 지점과 segment 출력 구현. |
| 다음 작업 ID | FEAT-04 |
| 의미·옵션·한계 | 참조 docstring의 누적 구간 설명과 실제 curr 초기화 코드 사이 차이가 있어 출력 정의를 실행 반례로 확인해야 한다. 이번 작업에서는 upstream 실행 검증하지 않았다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/concept_drift/algorithm.py :: apply`
- 변형 `pm4py/algo/concept_drift/algorithm.py :: Variants` → `BOSE`

## PM-ADV-017

**두 로그·모델의 확률적 trace 언어가 얼마나 다른가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 두 유한 확률 trace 언어와 trace 간 운송 비용 설정. |
| 확인할 출력 | 설정한 비용과 확률 질량에 대한 Earth Mover's Distance. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 언어 확률 질량·trace 거리 비용·최적 수송·잘린 언어 질량·공집합 계약 구현. |
| 다음 작업 ID | FEAT-04 |
| 의미·옵션·한계 | Selector명 PYEMD는 함수 구현을 식별한다. 실제 내부 EMDCalculator/POTEMDCalculator 선택과 일반 solver 경계는 별도이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: compute_emd`
- `pm4py/algo/evaluation/earth_mover_distance/algorithm.py :: apply`
- 변형 `pm4py/algo/evaluation/earth_mover_distance/algorithm.py :: Variants` → `PYEMD`

## PM-ADV-018

**질문 문장과 가장 유사한 case·event를 embedding으로 선택하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case/event 표본·질문 문장·embedding 모델과 k. |
| 확인할 출력 | 질문과 유사한 상위 k개 case/event 및 유사도 선택 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 검색 대상·cosine similarity·top-k 동률·모델 판본 및 실행 계층 결정. |
| 다음 작업 ID | FEAT-02, SCOPE-01 |
| 의미·옵션·한계 | Embedding 생성과 검색은 일반 프로세스 필터의 정의를 대체하지 않는다. 엔진 기능/Schumpeter 연동/선택 adapter 중 처분 미정. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/trace_encodings/algorithm.py :: keep_top_k_per_similarity`
- `pm4py/algo/transformation/to_embeddings/algorithm.py :: keep_top_k_per_similarity`
- 변형 `pm4py/algo/transformation/trace_encodings/algorithm.py :: Variants` → `CASES_TRANSFORMERS`, `EVENTS_TRANSFORMERS`

## PM-ORG-001

**누가 누구에게 업무를 인계하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Resource가 기록된 case 로그와 인계 거리·정규화 설정. |
| 확인할 출력 | 자원 간 handover 가중 network. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Resource·순서·인계 거리·정규화·self-loop·결측 자원 계약과 network 계산 구현. |
| 다음 작업 ID | ORG-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/org.py :: discover_handover_of_work_network`
- `pm4py/algo/organizational_mining/sna/algorithm.py :: apply`
- 변형 `pm4py/algo/organizational_mining/sna/algorithm.py :: Variants` → `HANDOVER_LOG`, `HANDOVER_PANDAS`

## PM-ORG-002

**같은 case에서 어떤 자원들이 함께 일하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Resource가 기록된 case 로그와 공동 참여 집계 설정. |
| 확인할 출력 | 같은 case에서 함께 일한 자원 쌍의 가중 network. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 공동 참여 집합·중복 기여·분모·단독 참여 사례 처리 구현. |
| 다음 작업 ID | ORG-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/org.py :: discover_working_together_network`
- `pm4py/algo/organizational_mining/sna/algorithm.py :: apply`
- 변형 `pm4py/algo/organizational_mining/sna/algorithm.py :: Variants` → `WORKING_TOGETHER_LOG`, `WORKING_TOGETHER_PANDAS`

## PM-ORG-003

**업무를 맡겼다가 돌아오는 subcontracting 관계는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Resource 순서가 있는 case 로그와 subcontracting 거리 설정. |
| 확인할 출력 | 위임 후 돌아오는 자원 관계의 가중 network. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | R1→R2→R1 패턴과 사이 거리·중첩·정규화 정의 구현. |
| 다음 작업 ID | ORG-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/org.py :: discover_subcontracting_network`
- `pm4py/algo/organizational_mining/sna/algorithm.py :: apply`
- 변형 `pm4py/algo/organizational_mining/sna/algorithm.py :: Variants` → `SUBCONTRACTING_LOG`, `SUBCONTRACTING_PANDAS`

## PM-ORG-004

**활동 구성을 기준으로 어떤 자원이 유사한가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 로그의 resource·activity와 유사도 설정. |
| 확인할 출력 | 자원별 활동 구성과 자원 쌍 유사도 network. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Resource×activity 행렬·유사도·0 벡터·동률·정규화 구현. |
| 다음 작업 ID | ORG-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/org.py :: discover_activity_based_resource_similarity`
- `pm4py/algo/organizational_mining/sna/algorithm.py :: apply`
- 변형 `pm4py/algo/organizational_mining/sna/algorithm.py :: Variants` → `JOINTACTIVITIES_LOG`, `JOINTACTIVITIES_PANDAS`

## PM-ORG-005

**활동 집합을 수행하는 조직 역할을 발견하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Resource×activity 빈도와 역할 병합 threshold. |
| 확인할 출력 | 활동·자원 구성으로 표현한 조직 역할 집합. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 초기 역할·multiset similarity·병합 threshold·동률 및 역할별 근거 구현. |
| 다음 작업 ID | ORG-02 |
| 의미·옵션·한계 | LOG/PANDAS는 동일 업무 질문의 입력 실행 경로이며 두 독립 알고리즘으로 자동 분리하지 않는다. 추가 reference_symbols의 전처리·tree 순회·집합/병합 helper는 해당 계산 내부 경로이며 별도 알고리즘 수로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/org.py :: discover_organizational_roles`
- `pm4py/algo/organizational_mining/roles/algorithm.py :: apply`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: get_sum_from_dictio_values`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: normalize_role`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: find_multiset_intersection`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: find_multiset_union`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: find_role_similarity`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: aggregate_roles_iteration`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: aggregate_roles_algorithm`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: get_initial_roles`
- `pm4py/algo/organizational_mining/roles/common/algorithm.py :: apply`
- 변형 `pm4py/algo/organizational_mining/roles/algorithm.py :: Variants` → `LOG`, `PANDAS`

## PM-ORG-006

**선택한 속성의 인계 network 빈도·시간을 분석하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그와 source/target 속성·edge 속성·시간 집계 설정. |
| 확인할 출력 | 속성 간 network와 edge별 빈도 또는 성능 값. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Source/target node·edge attribute·순서·시간 집계·business hours 계약 구현. |
| 다음 작업 ID | ORG-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/org.py :: discover_network_analysis`
- `pm4py/algo/organizational_mining/network_analysis/algorithm.py :: apply`
- 변형 `pm4py/algo/organizational_mining/network_analysis/algorithm.py :: Variants` → `DATAFRAME`

## PM-ORG-007

**발견한 조직 집단의 focus·stake·coverage·기여를 진단하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 로그와 조직 집단·역할 또는 clustering 결과. |
| 확인할 출력 | 집단별 focus·stake·coverage·member contribution 진단. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 조직 집단별 relative focus/stake/coverage/member contribution 수식·분모·중복 구성원 구현. |
| 다음 작업 ID | ORG-01, ORG-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/organizational_mining/local_diagnostics/algorithm.py :: apply_from_clustering_or_roles`
- `pm4py/algo/organizational_mining/local_diagnostics/algorithm.py :: apply_from_group_attribute`

## PM-ORG-008

**자원별 활동 종류·빈도·완료 case와 기여 비율은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Resource가 기록된 로그와 자원·활동·시간창 선택. |
| 확인할 출력 | 자원별 활동/완료 case 집계와 해당 비율. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 시간창·resource 참여·case 완료 기준별 원시 집계와 분모 구현. |
| 다음 작업 ID | ORG-02 |
| 의미·옵션·한계 | resource_profiles의 log/pandas는 type dispatch이다. Variants Enum이 없으므로 가짜 selector를 만들지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: distinct_activities`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: activity_frequency`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: activity_completions`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: case_completions`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: fraction_case_completions`

## PM-ORG-009

**자원의 평균 workload와 multitasking 정도는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 자원별 활동 interval 또는 시작 추정 정책과 시간창. |
| 확인할 출력 | 평균 workload·multitasking 및 그 시간 모집단. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 명시적 실행 interval·겹침·busy 합집합·capacity 기준 계산과 inferred start 정책 구현. |
| 다음 작업 ID | ORG-03 |
| 의미·옵션·한계 | 참조는 start 시각이 없을 때 이전 이벤트에서 시작을 추정하는 경로가 있다. PIX에서는 관측 interval과 추정 interval을 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: average_workload`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: multitasking`

## PM-ORG-010

**자원이 수행한 활동·case의 평균 소요시간은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 시작/완료가 있는 로그와 자원·활동·시간창. |
| 확인할 출력 | 자원별 평균 활동 기간과 참여 case 기간. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 자원·활동·case별 시간 모집단·시작/끝·미완료·이상치 집계 구현. |
| 다음 작업 ID | ORG-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: average_duration_activity`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: average_case_duration`

## PM-ORG-011

**자원 간 공동 참여와 사회적 위치를 수치화하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Resource가 기록된 case 로그와 대상 자원·시간창. |
| 확인할 출력 | 자원 간 interaction 및 social position 수치. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 공동 case·참여 비율·상호작용 및 social position 수식과 분모 구현. |
| 다음 작업 ID | ORG-01, ORG-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: interaction_two_resources`
- `pm4py/algo/organizational_mining/resource_profiles/algorithm.py :: social_position`

## PM-SIM-001

**Petri net이 허용하는 유한 실행을 생성·열거하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net·초기/최종 marking과 생성 수·seed·탐색 한도. |
| 확인할 출력 | 생성하거나 열거한 trace와 완료·deadlock·한도 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 발화 선택·초기/종료 marking·seed·loop 한도·deadlock·부분 생성 결과 구현. |
| 다음 작업 ID | SIM-01 |
| 의미·옵션·한계 | PIX fire/is_final은 기반 primitive이며 로그 생성/열거 playout 기능은 없다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/sim.py :: play_out`
- `pm4py/algo/simulation/playout/petri_net/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/petri_net/algorithm.py :: Variants` → `BASIC_PLAYOUT`, `EXTENSIVE`

## PM-SIM-002

**확률과 시간 분포를 가진 Petri net 실행을 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net·marking·stochastic map 및 seed/생성 설정. |
| 확인할 출력 | 분기와 처리시간을 표본 추출한 timestamp 포함 실행 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Stochastic map·분기 가중치·duration·seed·가정/학습 분포 구분 구현. |
| 다음 작업 ID | SIM-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/simulation/playout/petri_net/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/petri_net/algorithm.py :: Variants` → `STOCHASTIC_PLAYOUT`

## PM-SIM-003

**Process tree로부터 무작위·전체·top-bottom 실행을 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Process tree와 playout variant·생성 수·loop/탐색 한도. |
| 확인할 출력 | Tree 의미에 따라 생성하거나 열거한 trace 집합. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Operator별 실행·병렬 interleaving·loop 한도·표본 선택 정책 구현. |
| 다음 작업 ID | SIM-01, SIM-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/sim.py :: play_out`
- `pm4py/algo/simulation/playout/process_tree/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/process_tree/algorithm.py :: Variants` → `BASIC_PLAYOUT`, `EXTENSIVE`, `TOPBOTTOM`

## PM-SIM-004

**DFG의 시작·끝·전이 빈도로 실행을 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | DFG·시작/끝 빈도와 길이·수량·seed 제한. |
| 확인할 출력 | DFG 전이 확률에 따라 생성한 실행 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG 경계·경로 확률·종료 조건·잘린 질량·seed와 trace 생성 구현. |
| 다음 작업 ID | SIM-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/sim.py :: play_out`
- `pm4py/algo/simulation/playout/dfg/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/dfg/algorithm.py :: Variants` → `CLASSIC`

## PM-SIM-005

**DFG 경로에 성능 시간을 붙여 실행을 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 빈도/성능 DFG와 시작/끝 정보·시간 생성 설정. |
| 확인할 출력 | DFG 경로와 duration에 따른 timestamp 포함 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG 전이별 duration 분포·시각 생성·미관측 간격·seed 구현. |
| 다음 작업 ID | SIM-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/simulation/playout/dfg/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/dfg/algorithm.py :: Variants` → `PERFORMANCE`

## PM-SIM-006

**Declare 규칙을 만족하는 유한 trace를 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Declare 규칙 모델과 활동 집합·trace 길이/수량 제한. |
| 확인할 출력 | 규칙을 만족하도록 생성한 유한 trace 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 규칙별 생성 의미·길이 한도·모순/빈 언어·표본과 완전 열거 구분 구현. |
| 다음 작업 ID | SIM-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/simulation/playout/declare/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/declare/algorithm.py :: Variants` → `CLASSIC`

## PM-SIM-007

**Object-centric Petri net의 실제 객체 binding 실행을 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN·초기/최종 OC marking과 activity별 binding·branching 한도. |
| 확인할 출력 | 유효 binding sequence, OCEL 또는 허용 실행 존재 판정. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Binding sequence 열거·초기/최종 OC marking·binding 한도·객체 ID 재사용·OCEL 생성 구현. |
| 다음 작업 ID | SIM-01 |
| 의미·옵션·한계 | 2.7.23.8 배포판에 실제 memoized 탐색 구현이 있다. MAX_BINDINGS_PER_ACTIVITY 및 branching factor 제한을 가진 유한 문제이며 PIX의 binding enumeration 자체가 이 생성기를 대체하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/simulation/playout/ocpn/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/ocpn/algorithm.py :: Variants` → `EXTENSIVE`

## PM-SIM-008

**Object-centric causal net의 객체 binding 실행을 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OC causal net·객체 집합과 binding/branching 한도. |
| 확인할 출력 | 유효 객체 binding sequence 또는 생성한 OCEL. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OC causal net 상태·binding 의미와 생성기의 모델 선행 작업을 상세 플랜에 연결하고 한도별 OCEL 생성 구현. |
| 다음 작업 ID | SIM-01, SCOPE-01 |
| 의미·옵션·한계 | OCPN과 별도 모델이다. 실제 extensive 구현 확인; 새 모델을 기존 OCPN 명칭으로 흡수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/simulation/playout/oc_causal_net/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/playout/oc_causal_net/algorithm.py :: Variants` → `EXTENSIVE`

## PM-SIM-009

**자원 제약과 queue 아래에서 처리·대기 결과를 simulation하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·Petri net·marking과 도착/처리 분포·자원/queue 설정. |
| 확인할 출력 | Simulation 실행 기록과 대기·처리·throughput 시나리오 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | FIFO·capacity·stochastic timing·도착률·반복 seed·시나리오 비교 및 결과 분포 구현. |
| 다음 작업 ID | SIM-02, SIM-03 |
| 의미·옵션·한계 | PM4Py의 해당 variant 범위와 PIX 계획의 calendar 확장을 구분하며 simulation을 실제 인과 효과로 단정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/simulation/montecarlo/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/montecarlo/algorithm.py :: Variants` → `PETRI_SEMAPH_FIFO`

## PM-SIM-010

**설정한 크기와 operator 비율의 인공 process tree를 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 수·깊이·operator 비율·중복 label·seed 설정. |
| 확인할 출력 | 설정에 따라 생성한 인공 process tree. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 깊이·활동 수·operator 비율·중복 label·seed·생성 중단 조건 구현. |
| 다음 작업 ID | SIM-04 |
| 의미·옵션·한계 | 합성 모델 생성 성공은 실제 프로세스 대표성을 증명하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/sim.py :: generate_process_tree`
- `pm4py/algo/simulation/tree_generator/algorithm.py :: apply`
- 변형 `pm4py/algo/simulation/tree_generator/algorithm.py :: Variants` → `BASIC`, `PTANDLOGGENERATOR`

## PM-STREAM-001

**도착하는 이벤트·trace를 등록한 계산기에 전달하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 도착하는 이벤트/trace와 listener·수신/완료 설정. |
| 확인할 출력 | 등록 계산기로 전달되는 관측과 수신 상태 또는 누적 stream. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 수신·listener·event ID·offset·완료 신호·중복과 오류 처리 계약 구현. |
| 다음 작업 ID | STREAM-01 |
| 의미·옵션·한계 | Live queue/dispatcher 제공과 Agent 실행 runtime 제공은 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/stream/live_event_stream.py :: LiveEventStream`
- `pm4py/streaming/stream/live_trace_stream.py :: LiveTraceStream`
- `pm4py/streaming/algo/interface.py :: StreamingAlgorithm`
- `pm4py/streaming/util/live_to_static_stream.py :: LiveToStaticStream`

## PM-STREAM-002

**XES·CSV를 이벤트·trace 단위 iterator로 공급하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | XES/CSV 입력과 키 mapping·event/trace iterator 선택. |
| 확인할 출력 | 원본 입력을 순차 공급하는 event 또는 trace iterator. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 형식별 streaming iterator·metadata·원본 순서·오류/종료·backpressure 구현. |
| 다음 작업 ID | STREAM-01 |
| 의미·옵션·한계 | PIX batch import의 스트림 내부 파싱 사용 여부와 공개 incremental 계산 입력 지원은 다르다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/importer/xes/importer.py :: apply`
- `pm4py/streaming/importer/csv/importer.py :: apply`
- 변형 `pm4py/streaming/importer/xes/importer.py :: Variants` → `XES_EVENT_STREAM`, `XES_TRACE_STREAM`
- 변형 `pm4py/streaming/importer/csv/importer.py :: Variants` → `CSV_EVENT_STREAM`

## PM-STREAM-003

**Dataframe·OCEL 이벤트를 분석별 stream으로 나누어 공급하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Dataframe 또는 OCEL 이벤트와 객체형별 listener mapping. |
| 확인할 출력 | 순차 이벤트 또는 객체별 flat event stream. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 표 기반 event iterator와 객체형·객체별 분배, 원본 ID·중복 기여·공동 참여 유지 계약 구현. |
| 다음 작업 ID | STREAM-01 |
| 의미·옵션·한계 | 참조 OCEL distributor는 객체별 flat event 복제이다. PIX의 joint OC 계산에 그 flat 결과를 원본 공동 참여인 것처럼 사용하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/conversion/from_pandas.py :: apply`
- `pm4py/streaming/conversion/from_pandas.py :: PandasDataframeAsIterable`
- `pm4py/streaming/conversion/ocel_flatts_distributor.py :: OcelFlattsDistributor`

## PM-STREAM-004

**새 이벤트가 오면 DFG 빈도와 시작·끝을 갱신하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case ID·activity가 있는 이벤트 stream과 상태 저장 설정. |
| 확인할 출력 | 갱신된 DFG·활동·시작/끝 빈도와 case별 진행 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case별 마지막 이벤트·DFG 변화·종료 상태와 정정 결과 구현. |
| 다음 작업 ID | STREAM-02, STREAM-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/algo/discovery/dfg/algorithm.py :: apply`
- 변형 `pm4py/streaming/algo/discovery/dfg/algorithm.py :: Variants` → `FREQUENCY`

## PM-STREAM-005

**Petri net token replay 상태를 이벤트마다 갱신하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 stream·Petri net·초기/최종 marking과 replay 설정. |
| 확인할 출력 | Case별 marking과 token 기반 conformance 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case별 marking·token 진단·완료 처리·revision/checkpoint 구현. |
| 다음 작업 ID | STREAM-02, STREAM-03 |
| 의미·옵션·한계 | PIX batch replay 구현과 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/algo/conformance/tbr/algorithm.py :: apply`
- 변형 `pm4py/streaming/algo/conformance/tbr/algorithm.py :: Variants` → `CLASSIC`

## PM-STREAM-006

**진행 중 실행의 temporal profile 위반을 갱신하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Timestamp 이벤트 stream·temporal profile·허용 편차 설정. |
| 확인할 출력 | Case별 temporal conformance와 위반 시간 관계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 시간 조건의 관측 상태·late event·미관측 응답·정정 구현. |
| 다음 작업 ID | STREAM-02, STREAM-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/algo/conformance/temporal/algorithm.py :: apply`
- 변형 `pm4py/streaming/algo/conformance/temporal/algorithm.py :: Variants` → `CLASSIC`

## PM-STREAM-007

**진행 중 실행의 Declare automaton 상태를 갱신하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 stream·Declare 규칙과 case 완료 정보. |
| 확인할 출력 | 규칙 automaton의 case별 진행·충족·위반 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Template별 automaton·pending/fulfilled/violation·closure·정정 구현. |
| 다음 작업 ID | STREAM-02, STREAM-03 |
| 의미·옵션·한계 | 참조 automata.py는 미지원 template에 dummy automaton을 반환하는 경로가 있다. 지원 이름만으로 전체 규칙 대응을 확정하지 않는다. PIX 열린 관측 규칙 평가는 streaming 상태 엔진이 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/algo/conformance/declare/algorithm.py :: apply`
- 변형 `pm4py/streaming/algo/conformance/declare/algorithm.py :: Variants` → `AUTOMATA`

## PM-STREAM-008

**진행 중 실행이 허용된 footprint 관계를 따르는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 stream과 허용 footprint 관계·시작/끝 집합. |
| 확인할 출력 | 관측 경로의 footprint 적합성 상태와 위반 관계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 온라인 relation·start/end·미완료·위반 누적 및 철회 구현. |
| 다음 작업 ID | STREAM-02, STREAM-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/algo/conformance/footprints/algorithm.py :: apply`
- 변형 `pm4py/streaming/algo/conformance/footprints/algorithm.py :: Variants` → `CLASSIC`

## PM-STREAM-009

**제한된 기억과 look-ahead로 online alignment를 근사하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 stream·모델 proxy와 look-ahead·decay·seed·탐색 한도. |
| 확인할 출력 | 제한된 proxy에 대한 온라인 근사 alignment와 비용/상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 유한 model proxy trie·look-ahead·decay·seed·탐색 한도·근사 상태와 오차 평가 구현. |
| 다음 작업 ID | STREAM-02, STREAM-03 |
| 의미·옵션·한계 | I Will Survive 근사 profile이다. PIX exact batch alignment 호출을 그대로 대응 완료로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/algo/conformance/alignments/algorithm.py :: apply`
- 변형 `pm4py/streaming/algo/conformance/alignments/algorithm.py :: Variants` → `APPROX_IWS`

## PM-STREAM-010

**온라인 계산 상태를 안전하게 저장하고 재시작하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 상태 dictionary 요청과 메모리/thread-safe/Redis backend 설정. |
| 확인할 출력 | 온라인 계산에 쓰는 상태 저장소와 저장·조회 동작. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | State store 경계·원자적 revision·offset/model/profile을 묶은 checkpoint와 멱등 복구 구현. |
| 다음 작업 ID | STREAM-01, STREAM-03 |
| 의미·옵션·한계 | 참조 selector는 dictionary backend이다. Redis 자체 재개발이나 참조에 없는 정확한 복구 보장을 전제하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/util/dictio/generator.py :: apply`
- 변형 `pm4py/streaming/util/dictio/generator.py :: Variants` → `CLASSIC`, `THREAD_SAFE`, `REDIS`

## PM-ADV-019

**제어흐름 variant 빈도를 privacy 정의에 따라 익명화하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 로그와 privacy 예산·prefix 길이·pruning 설정. |
| 확인할 출력 | 잡음과 pruning을 적용한 제어흐름 variant 또는 합성 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 새로 식별된 계산군의 출시 포함·단계·책임을 결정하고, 포함 시 epsilon·인접성·composition·pruning·출력 효용 검증 계획을 추가. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 단순 connector가 아닌 실제 계산군이다. 기존 79개 작업에 직접 대응 항목이 없어 누락되지 않도록 처분 미정으로 보존한다. 법적 보장이나 배포 의무를 주장하는 행이 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/privacy.py :: anonymize_differential_privacy`
- `pm4py/algo/anonymization/trace_variant_query/algorithm.py :: apply`
- 변형 `pm4py/algo/anonymization/trace_variant_query/algorithm.py :: Variants` → `LAPLACE`, `SACOFA`

## PM-ADV-020

**익명화한 제어흐름에 timestamp·속성을 privacy 정의 아래 결합하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 원본 로그·익명화한 제어흐름과 privacy 예산·속성 설정. |
| 확인할 출력 | 익명화한 timestamp·속성을 결합한 이벤트 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Contextual anonymization의 출시 범위와 작업을 결정하고 trace matching·속성 범위·noise·privacy 예산을 별도 검증. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | SACOFA→PRIPEL 결합 façade이며 두 계산의 보장은 실행값 비교만으로 입증되지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/privacy.py :: anonymize_differential_privacy`
- `pm4py/algo/anonymization/pripel/algorithm.py :: apply`
- 변형 `pm4py/algo/anonymization/pripel/algorithm.py :: Variants` → `PRIPEL`

## PM-EDGE-001

**외부 LLM 서비스에 분석 질문을 전달하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 사용자 질문·선택 LLM/API 모델과 호출 설정. |
| 확인할 출력 | 외부 모델의 응답 텍스트 또는 호출 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | PIX 엔진·선택 adapter·Schumpeter 추론 연결 중 책임과 제공 필요성을 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 외부 API 호출 wrapper이다. PM4Py 대체 의도로 모든 서비스 SDK를 PIX core에 재개발하기로 확정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/llm.py :: openai_query`
- `pm4py/llm.py :: google_query`
- `pm4py/llm.py :: anthropic_query`

## PM-EDGE-002

**로그·모델·지표를 사람이 읽거나 LLM에 제공할 텍스트로 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·OCEL·모델·지표·DB 스키마와 포함/생략·길이 설정. |
| 확인할 출력 | 사람 또는 LLM에게 제공할 설명 텍스트와 도메인/질의 지식. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 형식별 텍스트 adapter·집계/생략·원본 ID·근거·시간/길이 budget 계약과 제공 계층 결정. |
| 다음 작업 ID | VIEW-01, SCOPE-01 |
| 의미·옵션·한계 | 텍스트 abstraction은 외부 추론 호출과 분리된 데이터 표현 기능이다. 기존 JSON 결과가 이 13종 설명 adapter를 모두 제공하는 것은 아니다. PM/DB knowledge injection의 traditional/ocel20 및 pandas_duckdb/sqlite3_traditional은 module/type dispatch이므로 별도 Enum을 만들지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/llm.py :: abstract_dfg`
- `pm4py/llm.py :: abstract_variants`
- `pm4py/llm.py :: abstract_ocel`
- `pm4py/llm.py :: abstract_ocel_ocdfg`
- `pm4py/llm.py :: abstract_ocel_features`
- `pm4py/llm.py :: abstract_event_stream`
- `pm4py/llm.py :: abstract_petri_net`
- `pm4py/llm.py :: abstract_log_attributes`
- `pm4py/llm.py :: abstract_log_features`
- `pm4py/llm.py :: abstract_temporal_profile`
- `pm4py/llm.py :: abstract_case`
- `pm4py/llm.py :: abstract_declare`
- `pm4py/llm.py :: abstract_log_skeleton`
- `pm4py/algo/querying/llm/injection/algorithm.py :: apply`
- `pm4py/algo/querying/llm/injection/db_knowledge/algorithm.py :: apply`
- `pm4py/algo/querying/llm/injection/pm_knowledge/algorithm.py :: apply`
- `pm4py/algo/querying/llm/injection/db_knowledge/variants/pandas_duckdb.py :: apply`
- `pm4py/algo/querying/llm/injection/db_knowledge/variants/sqlite3_traditional.py :: apply`
- `pm4py/algo/querying/llm/injection/pm_knowledge/variants/traditional.py :: apply`
- `pm4py/algo/querying/llm/injection/pm_knowledge/variants/ocel20.py :: apply`

## PM-EDGE-003

**LLM이 제안한 패턴으로 trace를 군집화하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 로그와 LLM executor·활동/case 키. |
| 확인할 출력 | LLM 생성 패턴별 이름과 해당 case 하위 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | LLM 생성 regex의 해석·검증·군집 근거와 PIX/Schumpeter 책임 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 일반 수치 clustering과 별도 LLM orchestration이다. 참조 패턴 생성·적용 흐름의 존재를 기록하며 출시 필수로 자동 확정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/llm.py :: clustering`

## PM-EDGE-004

**자연어를 로그 질의·필터 SQL로 바꾸어 적용하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 자연어 요청·로그/DB와 LLM executor·질의 설정. |
| 확인할 출력 | 생성된 질의의 결과 표 또는 선택한 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 질의 표현·실행 adapter·원본 lineage와 외부 추론 책임 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | SQL 작성과 실행을 포함하는 orchestration 표면이며 CaseLog/OCEL 계산 자체와 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/llm.py :: nlp_to_log_query`
- `pm4py/llm.py :: nlp_to_log_filter`

## PM-EDGE-005

**데이터 가설과 검사 질의를 LLM으로 생성하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 분석할 로그와 가설 수·LLM/질의 설정. |
| 확인할 출력 | 생성된 분석 가설 및 이를 검사할 질의/결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 가설 생성·검증 결과·근거/반증 조건의 표현 및 Schumpeter 연동 여부 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | LLM 생성 가설이 process intelligence 계산의 검증된 결론을 뜻하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/llm.py :: automated_hypotheses_formulation`

## PM-EDGE-006

**프로세스 그림을 LLM으로 설명하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 프로세스 시각화 이미지와 질문·멀티모달 LLM 설정. |
| 확인할 출력 | 외부 모델이 생성한 그림 설명. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 그림·원본 계산 근거·외부 추론 입력의 연결과 책임 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | PIX native viewer 및 설명용 계산 결과와 멀티모달 LLM API 호출을 분리한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/llm.py :: explain_visualization`

## PM-EDGE-007

**Outlook 메일·캘린더를 event log 또는 OCEL로 수집하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 접근 가능한 Outlook 메일/캘린더와 추출 설정. |
| 확인할 출력 | 메일·일정 활동을 변환한 이벤트 표 또는 OCEL. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 데이터 수집 adapter의 제품 책임·제공 범위·ID/관계 mapping 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 2개 원천에 대한 log/OCEL façade 쌍이다. OCEL wrapper는 대응 log 추출과 변환을 사용하므로 별도 native 계산으로 중복 계수하지 않는다. 공통 algo.connectors.apply는 9개 원천의 문자열 dispatch로 연결한다. AVAILABLE_CONNECTORS의 outlook_mail_extractor 표기와 실제 outlook_mail 분기 차이는 실행 호환 검증 때 확인해야 한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/connectors.py :: extract_log_outlook_mails`
- `pm4py/connectors.py :: extract_log_outlook_calendar`
- `pm4py/connectors.py :: extract_ocel_outlook_mails`
- `pm4py/connectors.py :: extract_ocel_outlook_calendar`
- `pm4py/algo/connectors/algorithm.py :: apply`

## PM-EDGE-008

**Windows 이벤트와 Chrome·Firefox 방문 기록을 로그로 수집하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Windows 이벤트 또는 Chrome/Firefox history 경로·추출 설정. |
| 확인할 출력 | OS·브라우저 활동을 변환한 이벤트 표 또는 OCEL. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OS·browser 수집기를 PIX 선택 adapter/Schumpeter 수집 경계 중 배치할지 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 3개 원천의 6 façade이다. 이 표 작성은 실제 사용자 기록 수집이나 연결을 수행하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/connectors.py :: extract_log_windows_events`
- `pm4py/connectors.py :: extract_log_chrome_history`
- `pm4py/connectors.py :: extract_log_firefox_history`
- `pm4py/connectors.py :: extract_ocel_windows_events`
- `pm4py/connectors.py :: extract_ocel_chrome_history`
- `pm4py/connectors.py :: extract_ocel_firefox_history`

## PM-EDGE-009

**GitHub 이슈·활동을 로그로 수집하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | GitHub repository 식별과 API 접근·조회 설정. |
| 확인할 출력 | GitHub 활동을 변환한 이벤트 표 또는 OCEL. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 외부 서비스 수집 범위·pagination·ID/관계 mapping·제공 계층 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 외부 API connector이며 PIX core 계산 구현에 포함하기로 미리 확정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/connectors.py :: extract_log_github`
- `pm4py/connectors.py :: extract_ocel_github`

## PM-EDGE-010

**Camunda·SAP O2C·SAP 회계 데이터를 로그로 수집하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Camunda/SAP DB 연결 정보와 해당 스키마·prefix 설정. |
| 확인할 출력 | 업무 데이터를 변환한 이벤트 표 또는 OCEL. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 업무 DB 연결과 스키마별 mapping의 adapter 책임·제공 범위 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | 3개 원천의 log/OCEL 쌍이며 일반 SQL DBMS 자체 재개발과 다르다. 회사 시스템/API에 연결하지 않았다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/connectors.py :: extract_log_camunda_workflow`
- `pm4py/connectors.py :: extract_log_sap_o2c`
- `pm4py/connectors.py :: extract_log_sap_accounting`
- `pm4py/connectors.py :: extract_ocel_camunda_workflow`
- `pm4py/connectors.py :: extract_ocel_sap_o2c`
- `pm4py/connectors.py :: extract_ocel_sap_accounting`

## PM-EDGE-011

**마우스·키 입력을 live event로 수집하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 실행 중인 Windows 입력 수집기와 전달/기록 설정. |
| 확인할 출력 | 마우스·키 입력에 따른 활동 event stream. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 행동 수집기의 필요성·책임·배포 범위를 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | OS 수집 runtime으로서 PIX 계산 엔진과 경계가 다르다. 원천 구현 존재만 추적하며 실제 수집은 실행하지 않았다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/streaming/connectors/windows/click_key_logger.py :: WindowsEventLogger`

## PM-EDGE-012

**명령행으로 기존 분석 API를 호출하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 명령행 분석 명령·입력 경로·옵션. |
| 확인할 출력 | 대응 분석 API의 결과·저장 파일·종료 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | PIX CLI 제공 여부·명령/결과/오류 계약을 제품 표면으로 결정. |
| 다음 작업 ID | SCOPE-01 |
| 의미·옵션·한계 | CLI는 기존 API dispatch이며 새로운 계산군이 아니다. meta.py는 버전 metadata; HOF/data formatting/serialization 기능은 데이터·모델 담당 행에서 추적한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/cli.py :: cli_interface`

## PM-VIEW-001

**DFG의 빈도·성능·비용을 그림으로 설명하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | DFG와 빈도/성능/비용 지표·표시/내보내기 설정. |
| 확인할 출력 | 지표를 표시한 DFG 그림과 저장 가능한 화면/graph 결과. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 현재 빈도·근거 graph에 performance/cost 집계 adapter와 큰 그래프 탐색을 연결. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | PIX는 renderer-neutral graph+offline ELK/SVG로 계산과 layout을 분리한다. 참조 backend의 외형 복제는 완료 조건이 아니다. |

**현재 PIX 근거:** `pix.viewer.build_graph`, `pix.viewer.export_html`.
소스: [src/pix/viewer/adapter.py](../../../src/pix/viewer/adapter.py), [src/pix/viewer/export.py](../../../src/pix/viewer/export.py), [src/pix/viewer/assets/viewer.js](../../../src/pix/viewer/assets/viewer.js).
실행 기록: [E-VIEWER](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_dfg`
- `pm4py/vis.py :: save_vis_dfg`
- `pm4py/vis.py :: view_performance_dfg`
- `pm4py/vis.py :: save_vis_performance_dfg`
- `pm4py/visualization/dfg/visualizer.py :: apply`
- 변형 `pm4py/visualization/dfg/visualizer.py :: Variants` → `FREQUENCY`, `PERFORMANCE`, `COST`

## PM-VIEW-002

**Petri net의 구조·marking·replay/성능/alignment를 그림에 표현하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net·marking 및 선택한 replay/성능/alignment 진단. |
| 확인할 출력 | 모델 구조와 계산 annotation을 결합한 그림. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 현재 모델 identity·arc weight·marking 표현 위에 계산 정의별 annotation과 진단 연결을 추가. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | PIX build_model_graph는 model 구조를 표현하며 로그 통계를 추론하지 않는다. |

**현재 PIX 근거:** `pix.viewer.build_model_graph`, `pix.viewer.export_html`.
소스: [src/pix/viewer/model_adapter.py](../../../src/pix/viewer/model_adapter.py), [src/pix/viewer/export.py](../../../src/pix/viewer/export.py), [src/pix/viewer/assets/viewer.js](../../../src/pix/viewer/assets/viewer.js).
실행 기록: [E-VIEWER](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_petri_net`
- `pm4py/vis.py :: save_vis_petri_net`
- `pm4py/visualization/petri_net/visualizer.py :: apply`
- 변형 `pm4py/visualization/petri_net/visualizer.py :: Variants` → `WO_DECORATION`, `FREQUENCY`, `PERFORMANCE`, `FREQUENCY_GREEDY`, `PERFORMANCE_GREEDY`, `ALIGNMENTS`

## PM-VIEW-003

**OCDFG에서 객체형별 경로·분모·성능을 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCDFG와 객체형·분모·성능 지표·표시 설정. |
| 확인할 출력 | 객체형 경로와 해당 지표를 구분하는 OCDFG 그림. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 현재 event-pair/unique-object/occurrence 근거 표현을 성능·부분 로딩·대규모 drilldown으로 확장. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 참조에도 ELKJS variant가 있다. PM4Py를 Graphviz 단일 backend라고 묘사하지 않는다. |

**현재 PIX 근거:** `pix.viewer.build_graph`, `pix.viewer.export_html`.
소스: [src/pix/viewer/adapter.py](../../../src/pix/viewer/adapter.py), [src/pix/viewer/export.py](../../../src/pix/viewer/export.py), [src/pix/viewer/assets/viewer.js](../../../src/pix/viewer/assets/viewer.js).
실행 기록: [E-VIEWER](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_ocdfg`
- `pm4py/vis.py :: save_vis_ocdfg`
- `pm4py/visualization/ocel/ocdfg/visualizer.py :: apply`
- 변형 `pm4py/visualization/ocel/ocdfg/visualizer.py :: Variants` → `CLASSIC`, `ELKJS`

## PM-VIEW-004

**OCPN의 객체형·cardinality·marking과 성능을 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCPN·marking·cardinality와 선택한 성능/진단 정보. |
| 확인할 출력 | 객체형·arc 의미와 계산 annotation을 표현한 OCPN 그림. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 현재 구조·object cardinality·provenance 표현 위에 performance/replay 근거 annotation을 추가. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | PIX OCPN model adapter와 참조 BRACHMANN 표현의 대응은 부분적이며 계산 지표 동등성을 검증한 것은 아니다. |

**현재 PIX 근거:** `pix.viewer.build_model_graph`, `pix.viewer.export_html`.
소스: [src/pix/viewer/model_adapter.py](../../../src/pix/viewer/model_adapter.py), [src/pix/viewer/export.py](../../../src/pix/viewer/export.py), [src/pix/viewer/assets/viewer.js](../../../src/pix/viewer/assets/viewer.js).
실행 기록: [E-VIEWER](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_ocpn`
- `pm4py/vis.py :: save_vis_ocpn`
- `pm4py/visualization/ocel/ocpn/visualizer.py :: apply`
- 변형 `pm4py/visualization/ocel/ocpn/visualizer.py :: Variants` → `WO_DECORATION`, `BRACHMANN`

## PM-VIEW-005

**Process tree operator와 빈도 annotation을 직접 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Process tree와 operator·빈도 annotation·layout 설정. |
| 확인할 출력 | Operator와 child 구조를 유지한 tree 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Tree operator·child order·loop/parallel 의미와 계산 annotation adapter 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | PIX가 tree를 발견·저장할 수 있어도 현재 model viewer는 PN/OCPN만 받는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_process_tree`
- `pm4py/vis.py :: save_vis_process_tree`
- `pm4py/visualization/process_tree/visualizer.py :: apply`
- 변형 `pm4py/visualization/process_tree/visualizer.py :: Variants` → `WO_DECORATION`, `SYMBOLIC`, `FREQUENCY_ANNOTATION`

## PM-VIEW-006

**BPMN의 gateway·flow·layout을 읽고 저장하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | BPMN 모델과 layout/renderer·표시 설정. |
| 확인할 출력 | Gateway·flow 의미를 유지한 배치와 BPMN 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | BPMN 모델 의미와 graph adapter·접근성·export 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 참조 DAGREJS/BPMNIO_AUTO_LAYOUT은 대체 layout 경로이다. 모든 renderer를 재구현해야 한다는 요구로 자동 확대하지 않는다. 별도 BPMN layouter의 GRAPHVIZ/GRAPHVIZ_NEW는 node/edge 좌표를 갱신하는 layout 선택이며 새 발견 알고리즘은 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_bpmn`
- `pm4py/vis.py :: save_vis_bpmn`
- `pm4py/visualization/bpmn/visualizer.py :: apply`
- `pm4py/objects/bpmn/layout/layouter.py :: apply`
- 변형 `pm4py/visualization/bpmn/visualizer.py :: Variants` → `CLASSIC`, `DAGREJS`, `BPMNIO_AUTO_LAYOUT`
- 변형 `pm4py/objects/bpmn/layout/layouter.py :: Variants` → `GRAPHVIZ`, `GRAPHVIZ_NEW`

## PM-VIEW-007

**POWL의 부분순서·operator·중첩 구조를 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | POWL 모델과 중첩·표시 설정. |
| 확인할 출력 | 부분순서와 operator 구조를 표현한 POWL 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | POWL 의미·부분순서·operator와 상호작용 adapter 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 해당 visualizer는 Variants Enum 없이 함수 인자로 표현을 제어하므로 없는 Enum을 기입하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_powl`
- `pm4py/vis.py :: save_vis_powl`
- `pm4py/visualization/powl/visualizer.py :: apply`

## PM-VIEW-008

**Heuristics net의 dependency와 AND 관계를 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Heuristics net과 dependency/AND·표시 설정. |
| 확인할 출력 | 관계와 지표를 표시한 Heuristics net 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Heuristics 모델 adapter·지표·threshold·관계별 근거 표현 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_heuristics_net`
- `pm4py/vis.py :: save_vis_heuristics_net`
- `pm4py/visualization/heuristics_net/visualizer.py :: apply`
- 변형 `pm4py/visualization/heuristics_net/visualizer.py :: Variants` → `PYDOTPLUS`

## PM-VIEW-009

**Transition system과 prefix trie를 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Transition system 또는 prefix trie와 상태/빈도·표시 설정. |
| 확인할 출력 | 상태 전이 또는 prefix 분기 구조의 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 상태 identity·transition 빈도·prefix branch/종료의 별도 adapter 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_transition_system`
- `pm4py/vis.py :: save_vis_transition_system`
- `pm4py/vis.py :: view_prefix_tree`
- `pm4py/vis.py :: save_vis_prefix_tree`
- `pm4py/visualization/transition_system/visualizer.py :: apply`
- `pm4py/visualization/trie/visualizer.py :: apply`
- 변형 `pm4py/visualization/transition_system/visualizer.py :: Variants` → `VIEW_BASED`, `TRANS_FREQUENCY`
- 변형 `pm4py/visualization/trie/visualizer.py :: Variants` → `CLASSIC`

## PM-VIEW-010

**Alignment 단계와 footprint 비교를 표·행렬로 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Alignment 이동 목록 또는 footprint와 비교 대상. |
| 확인할 출력 | Alignment 단계 표 또는 footprint 관계/차이 행렬. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Log/model/synchronous move와 비용·한도, 관계 matrix 차이의 결과 adapter 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | PIX 결과 JSON에 alignment 근거가 있어도 이 표/행렬 viewer 기능은 아직 없다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_alignments`
- `pm4py/vis.py :: save_vis_alignments`
- `pm4py/vis.py :: view_footprints`
- `pm4py/vis.py :: save_vis_footprints`
- `pm4py/visualization/align_table/visualizer.py :: apply`
- `pm4py/visualization/footprints/visualizer.py :: apply`
- 변형 `pm4py/visualization/align_table/visualizer.py :: Variants` → `CLASSIC`
- 변형 `pm4py/visualization/footprints/visualizer.py :: Variants` → `COMPARISON`, `SINGLE`, `COMPARISON_SYMMETRIC`

## PM-VIEW-011

**조직·자원 network의 빈도·시간을 탐색하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | SNA 또는 network-analysis 결과와 빈도/시간·표시 설정. |
| 확인할 출력 | 자원·조직 관계와 지표를 표시한 network 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 조직 network의 지표·분모·근거와 상호작용 adapter 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 참조 SNA에는 PYVIS가 있다. 시각화 동작 대체와 동일 backend 사용 여부는 별도이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_sna`
- `pm4py/vis.py :: save_vis_sna`
- `pm4py/vis.py :: view_network_analysis`
- `pm4py/vis.py :: save_vis_network_analysis`
- `pm4py/visualization/sna/visualizer.py :: apply`
- `pm4py/visualization/network_analysis/visualizer.py :: apply`
- 변형 `pm4py/visualization/sna/visualizer.py :: Variants` → `NETWORKX`, `PYVIS`
- 변형 `pm4py/visualization/network_analysis/visualizer.py :: Variants` → `FREQUENCY`, `PERFORMANCE`

## PM-VIEW-012

**시간축에서 이벤트 분포와 경로별 performance spectrum을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트 좌표 또는 performance-spectrum 결과와 축·표시 설정. |
| 확인할 출력 | 이벤트 분포 dotted chart 또는 구간별 performance spectrum. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Dotted chart 좌표·범주·원본 근거와 performance spectrum 구간·부분 표본 표시 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | Spectrum 계산은 데이터/성능 행에서 추적하며 이 행은 표현·내보내기 책임이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_dotted_chart`
- `pm4py/vis.py :: save_vis_dotted_chart`
- `pm4py/vis.py :: view_performance_spectrum`
- `pm4py/vis.py :: save_vis_performance_spectrum`
- `pm4py/visualization/dotted_chart/visualizer.py :: apply`
- `pm4py/visualization/performance_spectrum/visualizer.py :: apply`
- 변형 `pm4py/visualization/dotted_chart/visualizer.py :: Variants` → `CLASSIC`
- 변형 `pm4py/visualization/performance_spectrum/visualizer.py :: Variants` → `NEATO`

## PM-VIEW-013

**Case 기간·이벤트 발생·속성 분포를 그래프로 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 기간·발생 시각·속성 분포와 bin/축 설정. |
| 확인할 출력 | 기간·발생량·분포를 표현한 통계 chart. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 분포 bin·timezone·표본·결측·수치 근거와 chart export 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_case_duration_graph`
- `pm4py/vis.py :: save_vis_case_duration_graph`
- `pm4py/vis.py :: view_events_per_time_graph`
- `pm4py/vis.py :: save_vis_events_per_time_graph`
- `pm4py/vis.py :: view_events_distribution_graph`
- `pm4py/vis.py :: save_vis_events_distribution_graph`
- `pm4py/visualization/graphs/visualizer.py :: apply`
- 변형 `pm4py/visualization/graphs/visualizer.py :: Variants` → `CASES`, `ATTRIBUTES`, `DATES`, `BARPLOT`

## PM-VIEW-014

**객체 연결·객체형 참여·interleaving을 그래프로 확인하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 객체 관계 graph·event-to-type 관계 또는 interleaving 결과. |
| 확인할 출력 | 객체/형별 관계와 연결을 표시한 graph. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체/event identity·관계 direction/qualifier·원본 참여와 interleaving 표현 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | OCDFG viewer의 객체형 edge와 객체별 관계 graph는 다르다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/vis.py :: view_object_graph`
- `pm4py/vis.py :: save_vis_object_graph`
- `pm4py/visualization/ocel/object_graph/visualizer.py :: apply`
- `pm4py/visualization/ocel/eve_to_obj_types/visualizer.py :: apply`
- `pm4py/visualization/ocel/interleavings/visualizer.py :: apply`
- 변형 `pm4py/visualization/ocel/object_graph/visualizer.py :: Variants` → `GRAPHVIZ`
- 변형 `pm4py/visualization/ocel/eve_to_obj_types/visualizer.py :: Variants` → `GRAPHVIZ`
- 변형 `pm4py/visualization/ocel/interleavings/visualizer.py :: Variants` → `GRAPHVIZ`

## PM-VIEW-015

**Decision tree와 variant별 duration을 설명하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Decision tree 또는 variant별 duration 자료와 표시 설정. |
| 확인할 출력 | 결정 조건 tree 또는 variant duration 비교 그림. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 결정 조건·학습 표본/분기 label과 variant duration 분포의 각 adapter 구현. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/visualization/decisiontree/visualizer.py :: apply`
- `pm4py/visualization/variants_duration/visualizer.py :: apply`
- 변형 `pm4py/visualization/decisiontree/visualizer.py :: Variants` → `CLASSIC`
- 변형 `pm4py/visualization/variants_duration/visualizer.py :: Variants` → `CLASSIC`

## PM-VIEW-016

**일반 graph 구조를 표현하고 저장하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 일반 directed graph와 node/edge·layout 설정. |
| 확인할 출력 | 일반 graph 그림과 저장 가능한 렌더링 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 일반 graph adapter가 필요한 범위를 결정하고 model/result identity와 의미를 유지. |
| 다음 작업 ID | VIEW-01, VIEW-02, VIEW-03 |
| 의미·옵션·한계 | NetworkX graph를 Graphviz로 바꾸는 편의 표면이다. PIX 전체 graph API의 임의 NetworkX 호환까지 자동 요구하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/visualization/networkx/visualizer.py :: apply`
- 변형 `pm4py/visualization/networkx/visualizer.py :: Variants` → `DIGRAPH`
