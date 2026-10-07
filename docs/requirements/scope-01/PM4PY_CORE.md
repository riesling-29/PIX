# SCOPE-01 세부 대체표 — PM4Py 발견·적합성·모델

기준일: **2026-09-14**. [전체 범례·증거·판정 경계](../2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md).
입력·출력은 대체할 기능을 검토하기 위한 계약이다. **현재 PIX가 이미 그 결과를 반환한다는 뜻은 아니다.** 현재 지원은 각 행의 구현·의미·소스·증거로 구분한다.
참조 경로와 symbol은 공식 배포 wheel의 위치다. wrapper·helper·backend는 추적을 위해 함께 표시하며 별도 계산 알고리즘으로 중복 집계하지 않는다.

| ID | 도메인에서 판단할 질문 | PIX 구현 | 의미 대응 | 다음 작업 |
|---|---|---|---|---|
| [PM-DISC-001](#pm-disc-001) | 기록된 활동열을 설명하는 noise-free Inductive Miner 모델은 무엇인가? | 부분 대응 | PIX 자체 정의 | DISC-01 |
| [PM-DISC-002](#pm-disc-002) | 낮은 빈도의 행동을 잡음으로 다룰 때 어떤 모델과 제외 근거가 나오는가? | 대응 구현 없음 | 미구현 | DISC-02 |
| [PM-DISC-003](#pm-disc-003) | 전체 trace 대신 DFG·시작·종료 정보만 주어졌을 때 어떤 모델을 발견하는가? | 대응 구현 없음 | 미구현 | DISC-02 |
| [PM-DISC-004](#pm-disc-004) | 기본 인과·독립 관계에서 Alpha Petri net을 발견할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-03 |
| [PM-DISC-005](#pm-disc-005) | 길이 1 loop 등을 처리하는 Alpha+ 모델은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-03 |
| [PM-DISC-006](#pm-disc-006) | Dependency와 AND threshold로 잡음을 제어한 Heuristics net은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-03, MODEL-02, MODEL-04 |
| [PM-DISC-007](#pm-disc-007) | Heuristics++의 빈도·성능·동시성 정의에 따른 발견 결과는 무엇인가? | 대응 구현 없음 | 미구현 | DISC-03, MODEL-02 |
| [PM-DISC-008](#pm-disc-008) | Trace를 설명하는 region 기반 ILP 모델은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-04, MODEL-02 |
| [PM-DISC-009](#pm-disc-009) | 후보 모델을 진화시키며 fitness 기반으로 선택한 모델은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-04, CONF-02, MODEL-02 |
| [PM-DISC-010](#pm-disc-010) | 부분순서를 표현하는 POWL 모델은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-05, MODEL-02 |
| [PM-DISC-011](#pm-disc-011) | 빈도 필터와 동시성 판단에서 classic Split Miner BPMN을 발견할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-05, MODEL-02 |
| [PM-DISC-012](#pm-disc-012) | Lifecycle 구간 겹침을 활용한 Split Miner 2 BPMN은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-05, IO-03, MODEL-02 |
| [PM-DISC-013](#pm-disc-013) | Inductive Miner 결과를 BPMN으로 제공할 수 있는가? | 부분 대응 | 일부 의미 겹침 | DISC-01, DISC-02, MODEL-04 |
| [PM-DISC-014](#pm-disc-014) | 로그 또는 모델에서 순서·병렬·시작·종료 footprints를 추출할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, MODEL-05 |
| [PM-DISC-015](#pm-disc-015) | DFG에서 Alpha 또는 Heuristics 방식의 causal 관계를 얻을 수 있는가? | 대응 구현 없음 | 미구현 | DISC-03, DISC-06 |
| [PM-DISC-016](#pm-disc-016) | 과거·미래의 제한된 관측 창으로 어떤 상태 전이가 보이는가? | 대응 구현 없음 | 미구현 | DISC-06, MODEL-02 |
| [PM-DISC-017](#pm-disc-017) | 관측 prefix를 공유하는 trie를 만들 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, MODEL-02 |
| [PM-DISC-018](#pm-disc-018) | 활동 쌍의 시간 관계에서 정상 범위 temporal profile을 발견할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, PERF-01, RULE-03 |
| [PM-DISC-019](#pm-disc-019) | 반복·선후·동시 출현 규칙의 log skeleton을 발견할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, RULE-03 |
| [PM-DISC-020](#pm-disc-020) | Support·confidence 조건을 만족하는 Declare 규칙은 무엇인가? | 대응 구현 없음 | 미구현 | DISC-06, RULE-01, RULE-03 |
| [PM-DISC-021](#pm-disc-021) | 활동·자원·시간 구간에서 어떤 작업이 batch로 묶이는가? | 대응 구현 없음 | 미구현 | DISC-06, PERF-01 |
| [PM-DISC-022](#pm-disc-022) | Case 식별이 불충분한 이벤트로부터 활동 간 흐름을 추정할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06 |
| [PM-DISC-023](#pm-disc-023) | 전체 모델 대신 자주 반복되는 국소 프로세스 모델과 품질을 찾을 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, CONF-01 |
| [PM-DISC-024](#pm-disc-024) | Case의 활동 순서에서 직접 후속 관계와 시작·종료·빈도를 얻을 수 있는가? | 부분 대응 | 일부 의미 겹침 | DISC-06, STAT-01, IO-02 |
| [PM-DISC-025](#pm-disc-025) | 직접 후속 관계의 소요시간 분포를 계산할 수 있는가? | 부분 대응 | 일부 의미 겹침 | PERF-01, PERF-04, IO-02 |
| [PM-DISC-026](#pm-disc-026) | 활동 삼중항과 edge별 case 속성 분포를 계산할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, STAT-01, IO-02 |
| [PM-CONF-001](#pm-conf-001) | Trace를 Petri net에 재생할 때 어떤 token이 부족하거나 남는가? | 부분 대응 | PIX 자체 정의 | CONF-01, CONF-02, CONF-06 |
| [PM-CONF-002](#pm-conf-002) | Backward silent 탐색을 사용하는 token replay 결과는 무엇인가? | 대응 구현 없음 | 미구현 | CONF-05, CONF-06 |
| [PM-CONF-003](#pm-conf-003) | Trace와 accepting Petri net 사이의 최소 비용 alignment는 무엇인가? | 부분 대응 | 명시한 좁은 범위 대응 | CONF-01, CONF-05, CONF-06 |
| [PM-CONF-004](#pm-conf-004) | Discounted edit 비용을 쓰는 Petri net alignment는 무엇인가? | 대응 구현 없음 | 미구현 | CONF-05 |
| [PM-CONF-005](#pm-conf-005) | 큰 trace에서 근사 alignment를 계산하고 오차·완료 범위를 설명할 수 있는가? | 대응 구현 없음 | 미구현 | CONF-05, CONF-06 |
| [PM-CONF-006](#pm-conf-006) | 분해한 Petri net을 조합해 alignment를 구할 수 있는가? | 대응 구현 없음 | 미구현 | CONF-05, MODEL-06 |
| [PM-CONF-007](#pm-conf-007) | Process tree 자체에 대한 정확·근사 alignment는 무엇인가? | 부분 대응 | 일부 의미 겹침 | CONF-05, MODEL-02 |
| [PM-CONF-008](#pm-conf-008) | DFG가 허용하는 경로와 trace의 alignment는 무엇인가? | 대응 구현 없음 | 미구현 | CONF-05 |
| [PM-CONF-009](#pm-conf-009) | Trace를 다른 관측 언어와 비교한 edit-distance alignment는 무엇인가? | 대응 구현 없음 | 미구현 | CONF-05 |
| [PM-CONF-010](#pm-conf-010) | 대표 variant 부분집합으로 conformance를 근사하고 집계 경계를 줄 수 있는가? | 대응 구현 없음 | 미구현 | CONF-05 |
| [PM-CONF-011](#pm-conf-011) | 로그에서 가장 멀리 떨어진 허용 행동과 anti-alignment precision은 무엇인가? | 대응 구현 없음 | 미구현 | CONF-05 |
| [PM-CONF-012](#pm-conf-012) | 여러 trace를 대표하도록 최대 거리를 줄이는 모델 행동은 무엇인가? | 대응 구현 없음 | 미구현 | CONF-05 |
| [PM-CONF-013](#pm-conf-013) | Token 재생의 적합성을 정규화 점수로 비교할 수 있는가? | 대응 구현 없음 | 미구현 | CONF-01, CONF-02 |
| [PM-CONF-014](#pm-conf-014) | 최적 alignment 비용을 기준 경로 비용으로 정규화할 수 있는가? | 대응 구현 없음 | 미구현 | CONF-01, CONF-02 |
| [PM-CONF-015](#pm-conf-015) | Replay 기반 escaping-transitions precision은 얼마인가? | 부분 대응 | PIX 자체 정의 | CONF-01, CONF-03 |
| [PM-CONF-016](#pm-conf-016) | Alignment 기반 ET precision과 alignment 후 automaton precision은 얼마인가? | 대응 구현 없음 | 미구현 | CONF-03 |
| [PM-CONF-017](#pm-conf-017) | DFG가 허용한 다음 행동 중 관측되지 않은 비율은 얼마인가? | 대응 구현 없음 | 미구현 | CONF-03 |
| [PM-CONF-018](#pm-conf-018) | 전이 방문 빈도에서 generalization을 계산할 수 있는가? | 대응 구현 없음 | 미구현 | CONF-04 |
| [PM-CONF-019](#pm-conf-019) | 모델 복잡성을 서로 다른 구조 지표로 비교할 수 있는가? | 대응 구현 없음 | 미구현 | CONF-04, MODEL-05 |
| [PM-CONF-020](#pm-conf-020) | 로그와 모델의 footprints 위반·fitness·precision은 무엇인가? | 대응 구현 없음 | 미구현 | RULE-03, CONF-01 |
| [PM-CONF-021](#pm-conf-021) | 발견한 temporal profile의 정상 시간 범위를 벗어난 사례는 무엇인가? | 대응 구현 없음 | 미구현 | RULE-02, RULE-03, PERF-01 |
| [PM-CONF-022](#pm-conf-022) | Declare 규칙을 만족하거나 위반한 trace와 activation은 무엇인가? | 부분 대응 | 일부 의미 겹침 | RULE-01, RULE-03 |
| [PM-CONF-023](#pm-conf-023) | Log skeleton 규칙을 어긴 case와 항목은 무엇인가? | 대응 구현 없음 | 미구현 | RULE-03 |
| [PM-CONF-024](#pm-conf-024) | 단일 trace가 tree 또는 Petri net에 적합한지 판정할 수 있는가? | 부분 대응 | 일부 의미 겹침 | CONF-01, CONF-06 |
| [PM-CONF-025](#pm-conf-025) | 여러 품질 지표를 한 번에 재현 가능한 보고서로 묶을 수 있는가? | 대응 구현 없음 | 미구현 | CONF-01, CONF-06 |
| [PM-MODEL-001](#pm-model-001) | Weighted Petri net의 marking에서 가능한 발화와 종료를 판정할 수 있는가? | 구현 있음 | 명시한 좁은 범위 대응 | MODEL-01 |
| [PM-MODEL-002](#pm-model-002) | Reset·inhibitor arc와 data guard를 가진 net을 해석할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-01, MODEL-02 |
| [PM-MODEL-003](#pm-model-003) | 확률 전이와 분포를 가진 Petri net을 표현할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-01, MODEL-02 |
| [PM-MODEL-004](#pm-model-004) | Tree·BPMN·POWL·Heuristics net·TS·trie 모델을 식별하고 읽을 수 있는가? | 부분 대응 | 일부 의미 겹침 | MODEL-01, MODEL-02 |
| [PM-MODEL-005](#pm-model-005) | Process tree를 실행 가능한 Petri net으로 변환할 수 있는가? | 부분 대응 | 명시한 좁은 범위 대응 | MODEL-04 |
| [PM-MODEL-006](#pm-model-006) | Process tree를 BPMN 또는 POWL로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-02, MODEL-04 |
| [PM-MODEL-007](#pm-model-007) | BPMN을 Petri net으로 변환하여 계산할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-02, MODEL-04 |
| [PM-MODEL-008](#pm-model-008) | Workflow net을 process tree 또는 BPMN으로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-04, MODEL-05 |
| [PM-MODEL-009](#pm-model-009) | Petri net 또는 BPMN을 POWL로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-04, MODEL-05 |
| [PM-MODEL-010](#pm-model-010) | POWL을 net 또는 tree로 바꾸면 어떤 행동이 보존되는가? | 대응 구현 없음 | 미구현 | MODEL-04 |
| [PM-MODEL-011](#pm-model-011) | Heuristics net·GeneticMatrix·trie를 Petri net으로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-02, MODEL-04 |
| [PM-MODEL-012](#pm-model-012) | DFG를 서로 다른 구조의 Petri net으로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-04 |
| [PM-MODEL-013](#pm-model-013) | 현재 marking에서 도달 가능한 전체 상태와 전이는 무엇인가? | 부분 대응 | 일부 의미 겹침 | MODEL-05 |
| [PM-MODEL-014](#pm-model-014) | 모델이 workflow-net 구조 조건을 만족하는가? | 대응 구현 없음 | 미구현 | MODEL-05 |
| [PM-MODEL-015](#pm-model-015) | Workflow net은 종료 가능성·dead transition·boundedness 등 soundness를 만족하는가? | 대응 구현 없음 | 미구현 | MODEL-05 |
| [PM-MODEL-016](#pm-model-016) | Marking equation으로 도달 비용 하한을 계산할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-05, CONF-05 |
| [PM-MODEL-017](#pm-model-017) | Split point를 가진 extended marking equation 하한은 얼마인가? | 대응 구현 없음 | 미구현 | MODEL-05, CONF-05 |
| [PM-MODEL-018](#pm-model-018) | Trace와 모델의 synchronous product를 구성할 수 있는가? | 부분 대응 | 일부 의미 겹침 | MODEL-04, CONF-05 |
| [PM-MODEL-019](#pm-model-019) | 모델을 최대 구성요소로 분해하고 다시 조합할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-06, CONF-05 |
| [PM-MODEL-020](#pm-model-020) | 불필요한 invisible 구조나 implicit place를 의미를 보존하며 제거할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-06, MODEL-05 |
| [PM-MODEL-021](#pm-model-021) | 모델을 graph로 전달하고 활동 label을 읽거나 바꿀 수 있는가? | 부분 대응 | 일부 의미 겹침 | MODEL-02, MODEL-04 |
| [PM-MODEL-022](#pm-model-022) | 두 모델이 행동·구조 관점에서 얼마나 비슷한가? | 대응 구현 없음 | 미구현 | MODEL-05, DISC-06 |
| [PM-MODEL-023](#pm-model-023) | 모델 embedding 또는 label 의미로 유사도와 label 매핑을 구할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-05, MODEL-04 |
| [PM-MODEL-024](#pm-model-024) | 지정 trace 분석에 불필요한 선택적 tree 부분을 줄일 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-06, CONF-05 |
| [PM-MODEL-025](#pm-model-025) | 입출력 marker group·cardinality로 객체 중심 causal net을 만들고 상태를 해석할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-01, MODEL-02 |
| [PM-MODEL-026](#pm-model-026) | 객체 token과 variable arc를 가진 OCPN을 구성하고 발화할 수 있는가? | 부분 대응 | PIX 자체 정의 | MODEL-01, MODEL-02, OCONF-01 |
| [PM-MODEL-027](#pm-model-027) | OCCausalNet을 OCPN으로 변환하면 어떤 제약이 유지되거나 손실되는가? | 대응 구현 없음 | 미구현 | MODEL-04, MODEL-01 |
| [PM-MODEL-028](#pm-model-028) | OCPN의 객체 흐름을 marker 기반 causal net으로 표현할 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-04 |
| [PM-MODEL-029](#pm-model-029) | OCPN을 type별 Petri net 중심의 발견 결과 표현으로 바꿀 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-04, MODEL-06 |

## PM-DISC-001

**기록된 활동열을 설명하는 noise-free Inductive Miner 모델은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열·빈 trace·classifer 선택과 noise-free 발견 설정. |
| 확인할 출력 | 관측 활동열을 설명하는 process tree 또는 그로부터 변환한 Petri net·초기/최종 marking. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PM4Py IM의 strict-sequence·fallthrough·빈 trace 정책과 PIX 프로파일을 분리 대조하고 수용 언어 반례를 추가한다. |
| 다음 작업 ID | DISC-01 |
| 의미·옵션·한계 | pix.im.v1은 실제 log 기반 IM 프로파일이다. pix.inductive_cut.v1은 더 보수적인 별도 계산이며 참조 IM/IMf/IMd와 동등하다고 표기하지 않는다. |

**현재 PIX 근거:** `discover_process_tree`, `process_tree_to_petri_net`.
소스: [src/pix/compute/discovery.py](../../../src/pix/compute/discovery.py), [src/pix/contracts/discovery.py](../../../src/pix/contracts/discovery.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_process_tree_inductive`
- `pm4py/discovery.py :: discover_petri_net_inductive`
- `pm4py/algo/discovery/inductive/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/inductive/algorithm.py :: Variants` → `IM`

## PM-DISC-002

**낮은 빈도의 행동을 잡음으로 다룰 때 어떤 모델과 제외 근거가 나오는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 빈도, noise threshold 및 발견 설정. |
| 확인할 출력 | 잡음 처리 정책을 적용한 process tree와 그 모델의 수용·제외 관측 범위. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Frequency filtering·cut·fallthrough와 제외 모집단을 구현하고 noise_threshold 경계 및 원본/학습 로그 적합성을 각각 검증한다. |
| 다음 작업 ID | DISC-02 |
| 의미·옵션·한계 | 현재 noise_threshold=0 전용 PIX IM으로 IMf를 지원한다고 계산하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/inductive/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/inductive/algorithm.py :: Variants` → `IMf`

## PM-DISC-003

**전체 trace 대신 DFG·시작·종료 정보만 주어졌을 때 어떤 모델을 발견하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 DFG·빈도·시작/종료 활동과 빈 trace에 관한 정보. |
| 확인할 출력 | DFG 정보에 근거해 발견한 process tree. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG 입력 구조·빈 trace 정보·경계·IMd cut과 분할을 구현하고 log 기반 IM과 정보 손실 차이를 검증한다. |
| 다음 작업 ID | DISC-02 |
| 의미·옵션·한계 | DFG 입력은 단순 backend 교체가 아니라 계산 입력 정보가 다른 변형이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/inductive/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/inductive/algorithm.py :: Variants` → `IMd`

## PM-DISC-004

**기본 인과·독립 관계에서 Alpha Petri net을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열 또는 인과 관계를 구성할 DFG·시작/종료 활동. |
| 확인할 출력 | Alpha 방식으로 만든 Petri net과 초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Alpha causal pair와 maximal pair·place 생성, boundary·short-loop 한계를 구현한다. |
| 다음 작업 ID | DISC-03 |
| 의미·옵션·한계 |  추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_petri_net_alpha`
- `pm4py/algo/discovery/alpha/algorithm.py :: apply`
- `pm4py/algo/discovery/alpha/algorithm.py :: apply_dfg`
- `pm4py/algo/discovery/alpha/algorithm.py :: is_polars_lazyframe`
- 변형 `pm4py/algo/discovery/alpha/algorithm.py :: Variants` → `ALPHA_VERSION_CLASSIC`

## PM-DISC-005

**길이 1 loop 등을 처리하는 Alpha+ 모델은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 활동 이름·순서 해석. |
| 확인할 출력 | 길이 1 loop 처리 등을 반영한 Alpha+ Petri net과 초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Alpha+의 one-length loop 제거·복원과 classic 차이를 별도 fixture로 구현한다. |
| 다음 작업 ID | DISC-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_petri_net_alpha_plus`
- `pm4py/algo/discovery/alpha/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/alpha/algorithm.py :: Variants` → `ALPHA_VERSION_PLUS`

## PM-DISC-006

**Dependency와 AND threshold로 잡음을 제어한 Heuristics net은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동·case·시각이 있는 로그 또는 DFG·활동/경계 빈도와 dependency·AND·빈도 threshold. |
| 확인할 출력 | Heuristics net 또는 이를 변환한 Petri net·초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동·edge threshold, dependency, 길이 1/2 loop, AND measure와 Heuristics net의 입출력 결합을 구현한다. |
| 다음 작업 ID | DISC-03, MODEL-02, MODEL-04 |
| 의미·옵션·한계 |  추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_heuristics_net`
- `pm4py/discovery.py :: discover_petri_net_heuristics`
- `pm4py/algo/discovery/heuristics/algorithm.py :: apply`
- `pm4py/algo/discovery/heuristics/algorithm.py :: apply_heu`
- `pm4py/algo/discovery/heuristics/algorithm.py :: apply_dfg`
- `pm4py/algo/discovery/heuristics/algorithm.py :: apply_heu_dfg`
- 변형 `pm4py/algo/discovery/heuristics/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-007

**Heuristics++의 빈도·성능·동시성 정의에 따른 발견 결과는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동·case·시작/완료 시각이 있는 로그와 Heuristics++ threshold. |
| 확인할 출력 | Heuristics++ 정의로 계산한 결합·동시성 정보가 있는 net과 선택한 변환 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Heuristics++ 전용 의존·결합 규칙과 입력 전처리 차이를 classic과 분리한다. |
| 다음 작업 ID | DISC-03, MODEL-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/heuristics/algorithm.py :: apply`
- `pm4py/algo/discovery/heuristics/algorithm.py :: apply_heu`
- 변형 `pm4py/algo/discovery/heuristics/algorithm.py :: Variants` → `PLUSPLUS`

## PM-DISC-008

**Trace를 설명하는 region 기반 ILP 모델은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 causal 관계·제약·목적함수 설정. |
| 확인할 출력 | Region 제약에서 구성한 Petri net과 초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Region/제약·목적함수·place 구성과 불가능/제한 결과를 자체 구현한다. |
| 다음 작업 ID | DISC-04, MODEL-02 |
| 의미·옵션·한계 | 수치 LP/MILP solver는 별도 선택 backend이며 PM4Py 실행 위임과 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_petri_net_ilp`
- `pm4py/algo/discovery/ilp/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/ilp/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-009

**후보 모델을 진화시키며 fitness 기반으로 선택한 모델은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 집단 크기·변이/선택·평가·seed·종료 설정. |
| 확인할 출력 | 선택된 genetic 모델 또는 Petri net·marking과 해당 탐색의 평가 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | GeneticMatrix 표현, 초기 집단·교차·변이·평가·selection·seed·종료 예산을 구현한다. |
| 다음 작업 ID | DISC-04, CONF-02, MODEL-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_petri_net_genetic`
- `pm4py/algo/discovery/genetic/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/genetic/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-010

**부분순서를 표현하는 POWL 모델은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 빈도가 있는 활동열과 POWL 발견 변형·filtering 설정. |
| 확인할 출력 | 부분순서·choice·loop를 표현하는 POWL 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 네 POWL 발견 변형의 cut·partial order·clustering·filtering 정책과 모델 의미를 구분 구현한다. |
| 다음 작업 ID | DISC-05, MODEL-02 |
| 의미·옵션·한계 | POWLDiscoveryVariant는 algorithm.py 밖에 정의된다. 네 변형은 단순 dataframe backend가 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_powl`
- `pm4py/algo/discovery/powl/algorithm.py :: apply`
- `pm4py/algo/discovery/powl/algorithm.py :: get_variant`
- 변형 `pm4py/algo/discovery/powl/inductive/variants/powl_discovery_varaints.py :: POWLDiscoveryVariant` → `TREE`, `BRUTE_FORCE`, `MAXIMAL`, `DYNAMIC_CLUSTERING`

## PM-DISC-011

**빈도 필터와 동시성 판단에서 classic Split Miner BPMN을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 로그 또는 사전 집계 DFG와 빈도·동시성·OR 처리 설정. |
| 확인할 출력 | Classic Split Miner가 발견한 BPMN 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG filtering·concurrency·split/join·OR 처리·BPMN 구조를 구현하고 gateway 의미를 검산한다. |
| 다음 작업 ID | DISC-05, MODEL-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_bpmn_split_miner`
- `pm4py/algo/discovery/split_miner/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/split_miner/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-012

**Lifecycle 구간 겹침을 활용한 Split Miner 2 BPMN은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case·활동·lifecycle·시각이 있는 로그와 동시성 임계값. |
| 확인할 출력 | Complete-event DFG와 구간 겹침을 반영한 SM2 BPMN 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Complete-event DFG와 overlap oracle, 고정 eta=1·inclusive join 유지·OR-split·self-loop 정책을 classic과 구별해 구현한다. |
| 다음 작업 ID | DISC-05, IO-03, MODEL-02 |
| 의미·옵션·한계 | 실제 2.7.23.8 wheel의 SM2 구현 확인. Java 도구와 동등하다는 참조 문서의 주장은 이번 조사에서 실행 검증하지 않았다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/split_miner/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/split_miner/algorithm.py :: Variants` → `SM2`

## PM-DISC-013

**Inductive Miner 결과를 BPMN으로 제공할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 Inductive Miner 발견 설정. |
| 확인할 출력 | 발견한 process tree를 변환한 BPMN 모델. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 선택한 IM profile의 발견과 process tree→BPMN 변환을 조합하고 provenance를 유지한다. |
| 다음 작업 ID | DISC-01, DISC-02, MODEL-04 |
| 의미·옵션·한계 | 별도 miner 수학 문제로 중복 계수하지 않는 발견+변환 facade이다. PIX에 BPMN 변환은 없다. |

**현재 PIX 근거:** `discover_process_tree`.
소스: [src/pix/compute/discovery.py](../../../src/pix/compute/discovery.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_bpmn_inductive`

## PM-DISC-014

**로그 또는 모델에서 순서·병렬·시작·종료 footprints를 추출할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·trace·DFG 또는 Petri net/marking·tree·POWL과 선택한 해석 범위. |
| 확인할 출력 | 순서·병렬·활동·시작/종료 등의 footprints를 전체 또는 trace별로 표현한 관계 집합. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Log/trace/DFG/tree/POWL/reachability별 footprints 정의를 구현하고 정보 수준별 차이를 표시한다. |
| 다음 작업 ID | DISC-06, MODEL-05 |
| 의미·옵션·한계 | LOG/DATAFRAME/POLARS는 표현 backend인 반면 trace별·전체·모델 기반은 다른 모집단/계산이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_footprints`
- `pm4py/algo/discovery/footprints/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/footprints/algorithm.py :: Variants` → `ENTIRE_EVENT_LOG`, `ENTIRE_DATAFRAME`, `TRACE_BY_TRACE`, `PETRI_REACH_GRAPH`, `PROCESS_TREE`, `POWL`, `DFG`, `POLARS_LAZYFRAMES`

## PM-DISC-015

**DFG에서 Alpha 또는 Heuristics 방식의 causal 관계를 얻을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동쌍 빈도가 있는 DFG와 causal 계산 방식. |
| 확인할 출력 | Alpha 또는 Heuristics 정의의 방향성 인과 관계와 해당 가중치. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 두 causal relation 정의와 symmetric/self edge·threshold 처리를 구현한다. |
| 다음 작업 ID | DISC-03, DISC-06 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/causal/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/causal/algorithm.py :: Variants` → `CAUSAL_ALPHA`, `CAUSAL_HEURISTIC`

## PM-DISC-016

**과거·미래의 제한된 관측 창으로 어떤 상태 전이가 보이는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 forward/backward 방향·window 크기·sequence/set/multiset 해석. |
| 확인할 출력 | 추상화한 관측 상태와 활동 전이로 구성한 transition system. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Forward/backward와 sequence/set/multiset view, window 크기·data 부착을 구현한다. |
| 다음 작업 ID | DISC-06, MODEL-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_transition_system`
- `pm4py/algo/discovery/transition_system/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/transition_system/algorithm.py :: Variants` → `VIEW_BASED`

## PM-DISC-017

**관측 prefix를 공유하는 trie를 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 활동 classifier. |
| 확인할 출력 | 공통 prefix를 공유하고 trace 종료를 표현하는 trie. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 빈 trace·종료와 빈도를 보존하는 prefix trie 및 event/classifier 매핑을 구현한다. |
| 다음 작업 ID | DISC-06, MODEL-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_prefix_tree`

## PM-DISC-018

**활동 쌍의 시간 관계에서 정상 범위 temporal profile을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동·시각과 시간차·업무시간 해석 설정. |
| 확인할 출력 | 활동쌍별 관측 시간차의 평균·표준편차를 담은 temporal profile. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 모든 관련 activity pair의 duration 모집단·평균·표준편차·business hour 정책과 결측을 구현한다. |
| 다음 작업 ID | DISC-06, PERF-01, RULE-03 |
| 의미·옵션·한계 | Log/pandas 분기는 backend이다. 현재 adjacent gap 측정으로 pairwise temporal profile 발견을 대체하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_temporal_profile`
- `pm4py/algo/discovery/temporal_profile/algorithm.py :: apply`

## PM-DISC-019

**반복·선후·동시 출현 규칙의 log skeleton을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 noise threshold. |
| 확인할 출력 | 선후·동시 출현·활동 빈도 규칙을 모은 log skeleton 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Equivalence/always-after/always-before/never-together/directly-follows/activity-frequency와 noise threshold를 구현한다. |
| 다음 작업 ID | DISC-06, RULE-03 |
| 의미·옵션·한계 |  추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_log_skeleton`
- `pm4py/algo/discovery/log_skeleton/algorithm.py :: apply`
- `pm4py/algo/discovery/log_skeleton/algorithm.py :: apply_from_variants_list`
- 변형 `pm4py/algo/discovery/log_skeleton/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-020

**Support·confidence 조건을 만족하는 Declare 규칙은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 후보 template·활동·support/confidence 설정. |
| 확인할 출력 | 선택 기준을 만족하는 Declare 규칙과 규칙별 support·confidence. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 참조의 existence/exactly-one/init/response/precedence/succession/alternate/chain/negative 계열을 template별 논리식·모집단으로 구현한다. |
| 다음 작업 ID | DISC-06, RULE-01, RULE-03 |
| 의미·옵션·한계 | 기존 PIX 수동 규칙 평가 5종은 규칙 발견 기능이 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_declare`
- `pm4py/algo/discovery/declare/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/declare/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-021

**활동·자원·시간 구간에서 어떤 작업이 batch로 묶이는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case·활동·자원·시작/완료 시각과 batch 간격·크기 기준. |
| 확인할 출력 | 활동·자원별 batch 구간·유형 및 참여 이벤트 집단. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 동일 resource/activity의 구간과 임계 간격으로 batch 집단·유형·참여 이벤트를 반환한다. |
| 다음 작업 ID | DISC-06, PERF-01 |
| 의미·옵션·한계 | LOG/PANDAS/POLARS는 입력 backend이며 별도 세 알고리즘으로 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_batches`
- `pm4py/algo/discovery/batches/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/batches/algorithm.py :: Variants` → `LOG`, `PANDAS`, `POLARS`

## PM-DISC-022

**Case 식별이 불충분한 이벤트로부터 활동 간 흐름을 추정할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동·시각이 있는 이벤트와 선택적으로 case 정보, correlation 변형 설정. |
| 확인할 출력 | 관측의 상관 관계로 추정한 DFG 빈도와 활동쌍 시간 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Precede/succeed와 시간차·빈도 기반 최적화 및 split/trace 기반 변형을 구분하고 추정 관계를 원본 확정 관계와 분리한다. |
| 다음 작업 ID | DISC-06 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: correlation_miner`
- `pm4py/algo/discovery/correlation_mining/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/correlation_mining/algorithm.py :: Variants` → `CLASSIC`, `CLASSIC_SPLIT`, `TRACE_BASED`

## PM-DISC-023

**전체 모델 대신 자주 반복되는 국소 프로세스 모델과 품질을 찾을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 후보 활동·모델 크기·탐색/품질 기준. |
| 확인할 출력 | 발견된 local process tree 목록과 모델별 국소 품질 통계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Local process tree 후보 확장·로그 투영·빈도/범위/품질 평가·pruning·상한과 반환 순위를 구현한다. |
| 다음 작업 ID | DISC-06, CONF-01 |
| 의미·옵션·한계 | 실제 wheel의 내부 공개 algorithm에 존재하지만 최상위 discovery.py facade 목록만 보면 누락된다. 계획 DISC-06의 추가 세부 대상이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/local_process_models/algorithm.py :: find_local_process_models`
- `pm4py/algo/discovery/local_process_models/metrics/quality_metrics.py :: evaluate_tree`
- 변형 `pm4py/algo/discovery/local_process_models/algorithm.py :: Variants` → `CLASSIC`

## PM-DISC-024

**Case의 활동 순서에서 직접 후속 관계와 시작·종료·빈도를 얻을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열 또는 명시한 객체 trace와 순서·classifer 해석. |
| 확인할 출력 | 직접 후속 관계별 빈도와 시작/종료 활동 빈도, 선택한 typed DFG 표현. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | CaseLog 원본 순서/classifier를 DFG 입력으로 직접 연결하고 경계 빈도·빈 case·typed 결과를 통일한다. |
| 다음 작업 ID | DISC-06, STAT-01, IO-02 |
| 의미·옵션·한계 | PIX discover_dfg는 OCEL/ComputationContext의 객체 trace를 사용한다. CaseLog→discovery/replay 연결이 존재한다는 사실만으로 case DFG facade가 완성된 것은 아니다. NATIVE/FREQUENCY/FREQUENCY_GREEDY는 같은 native alias; CLEAN은 dataframe 경로. |

**현재 PIX 근거:** `discover_dfg`, `case_traces`.
소스: [src/pix/compute/dfg.py](../../../src/pix/compute/dfg.py), [src/pix/event_log/adapters.py](../../../src/pix/event_log/adapters.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_dfg`
- `pm4py/discovery.py :: discover_directly_follows_graph`
- `pm4py/discovery.py :: discover_dfg_typed`
- `pm4py/algo/discovery/dfg/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/dfg/algorithm.py :: Variants` → `NATIVE`, `FREQUENCY`, `FREQUENCY_GREEDY`, `CLEAN`

## PM-DISC-025

**직접 후속 관계의 소요시간 분포를 계산할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동 순서·시각과 start/complete·집계·업무시간 설정. |
| 확인할 출력 | 직접 후속 edge별 소요시간 집계와 표본의 의미. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case 순서·start/complete·business time을 명시한 edge duration 집계와 평균/중앙값 등 통계를 연결한다. |
| 다음 작업 ID | PERF-01, PERF-04, IO-02 |
| 의미·옵션·한계 | PERFORMANCE_GREEDY는 performance alias. PIX gap/service 측정과 performance DFG의 표본·분모는 대조가 필요하다. |

**현재 PIX 근거:** `measure_temporal`.
소스: [src/pix/compute/temporal.py](../../../src/pix/compute/temporal.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/discovery.py :: discover_performance_dfg`
- `pm4py/algo/discovery/dfg/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/dfg/algorithm.py :: Variants` → `PERFORMANCE`, `PERFORMANCE_GREEDY`

## PM-DISC-026

**활동 삼중항과 edge별 case 속성 분포를 계산할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열 및 case 속성과 triple/속성 집계 선택. |
| 확인할 출력 | 연속 활동 삼중항 빈도 또는 DFG edge별 case 속성 분포. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Consecutive triple frequency와 DFG별 case attribute 값·집계를 별도 payload로 구현한다. |
| 다음 작업 ID | DISC-06, STAT-01, IO-02 |
| 의미·옵션·한계 | FREQ_TRIPLES와 CASE_ATTRIBUTES는 단순 DFG backend가 아닌 다른 집계 결과이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/dfg/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/dfg/algorithm.py :: Variants` → `FREQ_TRIPLES`, `CASE_ATTRIBUTES`

## PM-CONF-001

**Trace를 Petri net에 재생할 때 어떤 token이 부족하거나 남는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동열·weighted Petri net·초기/최종 marking과 재생 정책. |
| 확인할 출력 | Trace별 발화·도달 marking·missing/remaining/consumed/produced token 및 재생 진단. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | Silent search·동일 label 전이 선택·unknown activity·token flooding·최종 marking과 prefix 진단 정책을 비교하고 차이를 문서화한다. |
| 다음 작업 ID | CONF-01, CONF-02, CONF-06 |
| 의미·옵션·한계 | PIX은 deterministic bounded silent replay와 missing/remaining/consumed/produced 증거를 제공한다. PM4Py 모든 옵션이나 정규화 점수 동등성은 미확인이다. 추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** `replay_traces`.
소스: [src/pix/compute/replay.py](../../../src/pix/compute/replay.py), [src/pix/contracts/replay.py](../../../src/pix/contracts/replay.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: conformance_diagnostics_token_based_replay`
- `pm4py/conformance.py :: replay_prefix_tbr`
- `pm4py/algo/conformance/tokenreplay/algorithm.py :: apply`
- `pm4py/algo/conformance/tokenreplay/algorithm.py :: get_diagnostics_dataframe`
- 변형 `pm4py/algo/conformance/tokenreplay/algorithm.py :: Variants` → `TOKEN_REPLAY`

## PM-CONF-002

**Backward silent 탐색을 사용하는 token replay 결과는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동열·Petri net·초기/최종 marking과 backward 재생 설정. |
| 확인할 출력 | Backward 탐색으로 선택한 재생 전이·token 계수·도달 상태와 진단. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Backward map·재생 순서·진단의 참조 의미를 구현하거나 동일 업무 질문에 대한 대체 정책을 검산한다. |
| 다음 작업 ID | CONF-05, CONF-06 |
| 의미·옵션·한계 | TOKEN_REPLAY와 다른 참조 variant이며 현재 PIX forward closure 정책을 대응 완료로 표시하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/tokenreplay/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/tokenreplay/algorithm.py :: Variants` → `BACKWARDS`

## PM-CONF-003

**Trace와 accepting Petri net 사이의 최소 비용 alignment는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace 또는 로그·accepting Petri net·이동 비용과 탐색 한도. |
| 확인할 출력 | 최소 비용 log/model/synchronous 이동열·최종 상태와 최적성/탐색 완료 정보. |
| 현재 PIX | 부분 대응 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | Per-event/per-transition 비용·최적성·silent 비용·종료 marking과 탐색 한도를 고정하고 A*/memory/semantics 경로를 검증한다. |
| 다음 작업 ID | CONF-01, CONF-05, CONF-06 |
| 의미·옵션·한계 | PIX bounded Dijkstra는 지원하는 weighted P/T net·비음수 정수 이동 비용에서 최적 경로를 계산하고 제한 상태를 보고한다. 같은 최단경로 문제의 탐색 backend를 별도 수학 지표로 중복 계수하지 않는다. 네 참조 구현의 전체 옵션 parity는 미확인이다. 추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** `align_traces`.
소스: [src/pix/compute/conformance.py](../../../src/pix/compute/conformance.py), [src/pix/contracts/conformance.py](../../../src/pix/contracts/conformance.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: conformance_diagnostics_alignments`
- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: apply`
- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: apply_trace`
- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: apply_log`
- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: apply_multiprocessing`
- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: get_diagnostics_dataframe`
- 변형 `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: Variants` → `VERSION_DIJKSTRA_NO_HEURISTICS`, `VERSION_DIJKSTRA_LESS_MEMORY`, `VERSION_DIJKSTRA_SEMANTICS`, `VERSION_STATE_EQUATION_A_STAR`

## PM-CONF-004

**Discounted edit 비용을 쓰는 Petri net alignment는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace·Petri net·초기/최종 marking과 discount 비용 설정. |
| 확인할 출력 | Discounted 목적함수에 따른 alignment 이동열·비용·탐색 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 시간/길이별 discount 목적함수와 비용·한도·최적성 범위를 일반 alignment와 분리해 구현한다. |
| 다음 작업 ID | CONF-05 |
| 의미·옵션·한계 | Discounted A*는 단순 탐색 backend뿐 아니라 비용 정의가 다르다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: Variants` → `VERSION_DISCOUNTED_A_STAR`

## PM-CONF-005

**큰 trace에서 근사 alignment를 계산하고 오차·완료 범위를 설명할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace·Petri net·초기/최종 marking과 반복 축약/window/horizon 설정. |
| 확인할 출력 | 선택한 근사법의 alignment·비용과 적용 가능한 경계·완료 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Tandem repeat 축약/복원, sliding-window top-k, fixed-horizon 상태 유지와 보장·실패 조건을 변형별 구현한다. |
| 다음 작업 ID | CONF-05, CONF-06 |
| 의미·옵션·한계 | 최신 wheel에서 확인한 근사 변형 세 가지다. PIX의 한도 초과 partial 반환만으로 이 근사법을 지원한다고 보지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/alignments/petri_net/algorithm.py :: Variants` → `APPROX_TANDEM_REPEATS`, `APPROX_SLIDING_WINDOW`, `APPROX_FIXED_HORIZON`

## PM-CONF-006

**분해한 Petri net을 조합해 alignment를 구할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·Petri net·초기/최종 marking과 분해/재조합 설정. |
| 확인할 출력 | 재조합한 alignment·비용과 각 구성요소 계산을 연결한 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Maximal decomposition·local alignment·불일치 recomposition·전체 비용 보장을 구현한다. |
| 다음 작업 ID | CONF-05, MODEL-06 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/decomposed/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/alignments/decomposed/algorithm.py :: Variants` → `RECOMPOS_MAXIMAL`

## PM-CONF-007

**Process tree 자체에 대한 정확·근사 alignment는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace 또는 로그·process tree와 비용·직접 tree 탐색 변형. |
| 확인할 출력 | Tree 의미에 맞춘 alignment·비용과 정확/근사·탐색 상태. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Tree operator별 의미에 대한 graph search/DP/MILP/근사 분할을 정의하고 비용·종료·보장을 비교한다. |
| 다음 작업 ID | CONF-05, MODEL-02 |
| 의미·옵션·한계 | PIX의 tree→net→alignment는 지원 tree 의미의 조합 경로이다. 직접 tree algorithms와 성능·근사 정책까지 구현했다는 뜻은 아니다. |

**현재 PIX 근거:** `process_tree_to_petri_net`, `align_traces`.
소스: [src/pix/compute/discovery.py](../../../src/pix/compute/discovery.py), [src/pix/compute/conformance.py](../../../src/pix/compute/conformance.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/process_tree/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/alignments/process_tree/algorithm.py :: Variants` → `APPROXIMATED_ORIGINAL`, `SEARCH_GRAPH_PT`, `DYNAMIC_PROGRAMMING`, `MILP`

## PM-CONF-008

**DFG가 허용하는 경로와 trace의 alignment는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace·DFG·시작/종료 활동과 이동 비용. |
| 확인할 출력 | DFG 허용 경로에 대한 alignment 이동열과 비용. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG 시작/종료와 반복을 포함한 경로 의미·이동 비용·최종 상태를 구현한다. |
| 다음 작업 ID | CONF-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/dfg/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/alignments/dfg/algorithm.py :: Variants` → `CLASSIC`

## PM-CONF-009

**Trace를 다른 관측 언어와 비교한 edit-distance alignment는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 비교할 trace 집합과 기준 로그의 활동열 집합, edit 비용. |
| 확인할 출력 | 기준 활동열에 대한 최소 편집 alignment와 비용. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 모델이 아닌 reference log language와 최소 edit alignment·동률·빈 trace를 구현한다. |
| 다음 작업 ID | CONF-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/edit_distance/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/alignments/edit_distance/algorithm.py :: Variants` → `EDIT_DISTANCE`

## PM-CONF-010

**대표 variant 부분집합으로 conformance를 근사하고 집계 경계를 줄 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net과 대표 부분집합 선택·seed·근사 설정. |
| 확인할 출력 | 대표 활동열에서 복원한 alignment와 근사 적합성·집계 경계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 대표 선택·edit 복원·k-medoids/시뮬레이션 옵션·집계 bound와 seed를 구현한다. |
| 다음 작업 ID | CONF-05 |
| 의미·옵션·한계 | 최신 wheel의 APPROX_SUBSET은 단순 두 log 편집거리와 입력·근사 의미가 다르다. 추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/alignments/edit_distance/algorithm.py :: apply`
- `pm4py/algo/conformance/alignments/edit_distance/variants/approx_subset.py :: apply_with_summary`
- `pm4py/algo/conformance/alignments/edit_distance/algorithm.py :: apply_approximation`
- `pm4py/algo/conformance/alignments/edit_distance/algorithm.py :: apply_approximation_with_summary`
- 변형 `pm4py/algo/conformance/alignments/edit_distance/algorithm.py :: Variants` → `APPROX_SUBSET`

## PM-CONF-011

**로그에서 가장 멀리 떨어진 허용 행동과 anti-alignment precision은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그의 활동열 집합·accepting Petri net과 discount·epsilon·탐색 한도. |
| 확인할 출력 | 관측에서 먼 허용 실행인 anti-alignment와 거리·precision 경계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Discounted 최대 최소 거리·marking 한도·epsilon·반환 witness/precision 경계를 구현한다. |
| 다음 작업 ID | CONF-05 |
| 의미·옵션·한계 | 참조가 스스로 근사 lower-bound precision이라고 명시한다. 일반 최소 alignment와 목적함수가 다르며 무제한 순환을 유한 최적이라고 주장하지 않는다. 추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/antialignments/algorithm.py :: apply`
- `pm4py/algo/conformance/antialignments/algorithm.py :: apply_log`
- 변형 `pm4py/algo/conformance/antialignments/algorithm.py :: Variants` → `VERSION_DISCOUNTED_A_STAR`

## PM-CONF-012

**여러 trace를 대표하도록 최대 거리를 줄이는 모델 행동은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그의 활동열 집합·accepting Petri net과 discounted 거리·탐색 한도. |
| 확인할 출력 | 여러 trace에 대한 최대 거리를 줄이는 대표 모델 실행과 그 거리. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Multi-alignment의 minimax/discounted 비용·대표 행동·탐색 한도를 구현하고 anti-alignment와 분리한다. |
| 다음 작업 ID | CONF-05 |
| 의미·옵션·한계 |  추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/multialignments/algorithm.py :: apply`
- `pm4py/algo/conformance/multialignments/algorithm.py :: apply_log`
- 변형 `pm4py/algo/conformance/multialignments/algorithm.py :: Variants` → `VERSION_DISCOUNTED_A_STAR`

## PM-CONF-013

**Token 재생의 적합성을 정규화 점수로 비교할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net 또는 동일 정책으로 계산된 token 재생 결과. |
| 확인할 출력 | 적합 trace 비율·trace 평균·token 총계 기반의 정규화 fitness. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 초기/최종 token과 missing/consumed·remaining/produced, trace 평균/합계 비율·빈 분모를 명시한 점수를 구현한다. |
| 다음 작업 ID | CONF-01, CONF-02 |
| 의미·옵션·한계 | PIX raw token counts는 이미 있으나 normalized fitness public calculation은 없다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: fitness_token_based_replay`
- `pm4py/algo/evaluation/replay_fitness/algorithm.py :: apply`
- `pm4py/algo/evaluation/replay_fitness/algorithm.py :: evaluate`
- 변형 `pm4py/algo/evaluation/replay_fitness/algorithm.py :: Variants` → `TOKEN_BASED`

## PM-CONF-014

**최적 alignment 비용을 기준 경로 비용으로 정규화할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net·alignment 비용과 모델 최소 완주 기준 비용. |
| 확인할 출력 | Trace 평균·전체 합계 기반 정규화 alignment fitness와 적합 비율. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Best-worst/model-only 기준 비용·평균/합계 지표·불완전 분모의 unknown 상태를 구현한다. |
| 다음 작업 ID | CONF-01, CONF-02 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: fitness_alignments`
- `pm4py/algo/evaluation/replay_fitness/algorithm.py :: apply`
- `pm4py/algo/evaluation/replay_fitness/algorithm.py :: evaluate`
- 변형 `pm4py/algo/evaluation/replay_fitness/algorithm.py :: Variants` → `ALIGNMENT_BASED`

## PM-CONF-015

**Replay 기반 escaping-transitions precision은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net과 replay·prefix 가중치·enabled 해석. |
| 확인할 출력 | 재생 가능한 prefix의 escaping transition에 근거한 ET precision. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | Prefix 빈도·fit prefix·silent enabled closure·escaping edge·종료를 명시한 ET token profile을 추가한다. |
| 다음 작업 ID | CONF-01, CONF-03 |
| 의미·옵션·한계 | PIX occurrence-weighted enabled-prefix precision은 실제 계산이지만 ETConformance와 동일하다고 선언하지 않는다. |

**현재 PIX 근거:** `measure_prefix_precision`.
소스: [src/pix/compute/precision.py](../../../src/pix/compute/precision.py), [src/pix/contracts/precision.py](../../../src/pix/contracts/precision.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: precision_token_based_replay`
- `pm4py/algo/evaluation/precision/algorithm.py :: apply`
- 변형 `pm4py/algo/evaluation/precision/algorithm.py :: Variants` → `ETCONFORMANCE_TOKEN`

## PM-CONF-016

**Alignment 기반 ET precision과 alignment 후 automaton precision은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net과 alignment·prefix/automaton precision 설정. |
| 확인할 출력 | Alignment 기반 ET precision 또는 정렬된 모델 실행 automaton 기반 precision. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 적합하지 않은 prefix의 alignment, 모델 실행 투영, automaton 통계·weighting을 각 정의로 구현한다. |
| 다음 작업 ID | CONF-03 |
| 의미·옵션·한계 | AUTOMATON_AFTER_ALIGN은 최신 wheel에서 확인한 별도 precision variant다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: precision_alignments`
- `pm4py/algo/evaluation/precision/algorithm.py :: apply`
- 변형 `pm4py/algo/evaluation/precision/algorithm.py :: Variants` → `ALIGN_ETCONFORMANCE`, `AUTOMATON_AFTER_ALIGN`

## PM-CONF-017

**DFG가 허용한 다음 행동 중 관측되지 않은 비율은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그 활동열·DFG·시작/종료 활동. |
| 확인할 출력 | 허용 prefix에서 관측하지 않은 다음 활동에 근거한 DFG precision. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG의 허용 prefix·시작·종료·escaping activities와 occurrence 분모를 구현한다. |
| 다음 작업 ID | CONF-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/evaluation/precision/dfg/algorithm.py :: apply`

## PM-CONF-018

**전이 방문 빈도에서 generalization을 계산할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net과 token 재생 결과 또는 설정. |
| 확인할 출력 | 모델 전이의 방문 빈도·미방문 처리에 근거한 generalization 점수. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 미방문·silent 전이·재생 불완전성·frequency 기반 일반화 수식을 구현한다. |
| 다음 작업 ID | CONF-04 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: generalization_tbr`
- `pm4py/algo/evaluation/generalization/algorithm.py :: apply`
- 변형 `pm4py/algo/evaluation/generalization/algorithm.py :: Variants` → `GENERALIZATION_TOKEN`

## PM-CONF-019

**모델 복잡성을 서로 다른 구조 지표로 비교할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net과 지표 선택, 상태공간 기반 지표에 필요한 초기 marking. |
| 확인할 출력 | Arc-degree·extended Cardoso·extended cyclomatic 중 선택한 복잡성 지표. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Arc-degree·extended Cardoso·reachability 기반 cyclomatic 정의와 적용 모델·한도를 분리 구현한다. |
| 다음 작업 ID | CONF-04, MODEL-05 |
| 의미·옵션·한계 | 세 지표는 같은 이름의 backend가 아니라 서로 다른 구조량이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: simplicity_petri_net`
- `pm4py/algo/evaluation/simplicity/algorithm.py :: apply`
- 변형 `pm4py/algo/evaluation/simplicity/algorithm.py :: Variants` → `SIMPLICITY_ARC_DEGREE`, `EXTENDED_CARDOSO`, `EXTENDED_CYCLOMATIC`

## PM-CONF-020

**로그와 모델의 footprints 위반·fitness·precision은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그/trace footprints와 모델 footprints 및 비교 범위. |
| 확인할 출력 | 위반 관계·경계·길이 진단과 footprints fitness·precision. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 각 footprint 구성요소·trace/전체 모집단·start/end/min-length 진단과 점수 분모를 구현한다. |
| 다음 작업 ID | RULE-03, CONF-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: conformance_diagnostics_footprints`
- `pm4py/conformance.py :: fitness_footprints`
- `pm4py/conformance.py :: precision_footprints`
- `pm4py/algo/conformance/footprints/algorithm.py :: apply`
- 변형 `pm4py/algo/conformance/footprints/algorithm.py :: Variants` → `LOG_MODEL`, `LOG_EXTENSIVE`, `TRACE_EXTENSIVE`

## PM-CONF-021

**발견한 temporal profile의 정상 시간 범위를 벗어난 사례는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 시각이 있는 case 로그·temporal profile과 허용 표준편차 배수. |
| 확인할 출력 | 정상 시간 범위를 벗어난 활동쌍·case·관측 시간차와 편차 진단. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Zeta·표준편차 0·pairwise 시간·business hours와 event-level 위반 근거를 구현한다. |
| 다음 작업 ID | RULE-02, RULE-03, PERF-01 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: conformance_temporal_profile`
- `pm4py/algo/conformance/temporal_profile/algorithm.py :: apply`
- `pm4py/algo/conformance/temporal_profile/algorithm.py :: get_diagnostics_dataframe`

## PM-CONF-022

**Declare 규칙을 만족하거나 위반한 trace와 activation은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열 또는 명시한 객체 trace·Declare 규칙과 관측 종료 조건. |
| 확인할 출력 | Trace별 규칙 위반·충족 진단과 적용 template의 적합성 정보. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 참조 Declare 전체 template 평가와 case 모집단·vacuity·closed/open 경계를 구현한다. |
| 다음 작업 ID | RULE-01, RULE-03 |
| 의미·옵션·한계 | PIX Count/Precedence/Response/NotCoexistence/TimedResponse 일부 논리는 겹치지만 object trace 기반 자체 규칙이며 전체 Declare conformance가 아니다. 추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** `evaluate_constraints`.
소스: [src/pix/compute/constraints.py](../../../src/pix/compute/constraints.py), [src/pix/contracts/constraint.py](../../../src/pix/contracts/constraint.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: conformance_declare`
- `pm4py/algo/conformance/declare/algorithm.py :: apply`
- `pm4py/algo/conformance/declare/algorithm.py :: get_diagnostics_dataframe`
- 변형 `pm4py/algo/conformance/declare/algorithm.py :: Variants` → `CLASSIC`

## PM-CONF-023

**Log skeleton 규칙을 어긴 case와 항목은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열·log skeleton 모델과 평가 설정. |
| 확인할 출력 | Case별 skeleton 위반 항목·적합 여부 및 집계 진단. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 여섯 relation/frequency 규칙·noise와 deviation/fitness 진단을 구현한다. |
| 다음 작업 ID | RULE-03 |
| 의미·옵션·한계 |  추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: conformance_log_skeleton`
- `pm4py/algo/conformance/log_skeleton/algorithm.py :: apply`
- `pm4py/algo/conformance/log_skeleton/algorithm.py :: apply_from_variants_list`
- `pm4py/algo/conformance/log_skeleton/algorithm.py :: get_diagnostics_dataframe`
- 변형 `pm4py/algo/conformance/log_skeleton/algorithm.py :: Variants` → `CLASSIC`

## PM-CONF-024

**단일 trace가 tree 또는 Petri net에 적합한지 판정할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 단일 활동열과 process tree 또는 Petri net·초기/최종 marking. |
| 확인할 출력 | 선택한 적합성 정의에 따른 적합 판정과 평가 한도 상태. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Supported model별 replay/alignment 판정 경로를 명시하고 limited·unknown을 false/true와 분리한다. |
| 다음 작업 ID | CONF-01, CONF-06 |
| 의미·옵션·한계 | 편의 facade의 재사용 경로이며 새로운 독립 최적화 문제로 계수하지 않는다. |

**현재 PIX 근거:** `align_traces`, `replay_traces`, `process_tree_to_petri_net`.
소스: [src/pix/compute/conformance.py](../../../src/pix/compute/conformance.py), [src/pix/compute/replay.py](../../../src/pix/compute/replay.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/conformance.py :: check_is_fitting`

## PM-CONF-025

**여러 품질 지표를 한 번에 재현 가능한 보고서로 묶을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·accepting Petri net과 지표별 평가·가중치 설정. |
| 확인할 출력 | Fitness·precision·generalization·simplicity 및 명시한 조합 점수를 묶은 평가 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Fitness·precision·generalization·simplicity의 결과와 reference aggregate/f-score/weighting을 명시적으로 묶는다. |
| 다음 작업 ID | CONF-01, CONF-06 |
| 의미·옵션·한계 | 평가 orchestration facade는 underlying 계산과 중복 구현하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/evaluation/algorithm.py :: apply`

## PM-MODEL-001

**Weighted Petri net의 marking에서 가능한 발화와 종료를 판정할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Weighted P/T net·현재 marking과 선택한 전이 또는 종료 marking. |
| 확인할 출력 | Enabled 전이 집합·발화 뒤 marking·종료 여부. |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | Supported weighted P/T firing·marking 계약을 참조와 대조하고 weak_execute처럼 enable 검사를 우회하는 helper는 별도 정책으로 분리한다. |
| 다음 작업 ID | MODEL-01 |
| 의미·옵션·한계 | 지원하는 ordinary weighted P/T net 발화 의미는 구현돼 있다. PM4Py mutable class/API·weak execution·모든 arc subtype 호환은 이 행의 완료 의미가 아니다. |

**현재 PIX 근거:** `PetriNet`, `Marking`, `is_enabled`, `enabled_transitions`, `fire`, `is_final`.
소스: [src/pix/contracts/models.py](../../../src/pix/contracts/models.py), [src/pix/compute/model_semantics.py](../../../src/pix/compute/model_semantics.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/petri_net/obj.py :: PetriNet`
- `pm4py/objects/petri_net/obj.py :: Marking`
- `pm4py/objects/petri_net/semantics.py :: is_enabled`
- `pm4py/objects/petri_net/semantics.py :: execute`
- `pm4py/objects/petri_net/semantics.py :: weak_execute`
- `pm4py/objects/petri_net/semantics.py :: enabled_transitions`
- `pm4py/analysis.py :: get_enabled_transitions`
- `pm4py/analysis.py :: generate_marking`

## PM-MODEL-002

**Reset·inhibitor arc와 data guard를 가진 net을 해석할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Reset/inhibitor/data net·marking·event data와 발화 또는 타입 변환 요청. |
| 확인할 출력 | 해당 arc/guard 의미의 enabled·발화 상태 또는 명시한 타입으로 변환한 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Reset/inhibitor/data guard 타입·enabled/firing·변환 손실·지원 계산 capability를 구현한다. |
| 다음 작업 ID | MODEL-01, MODEL-02 |
| 의미·옵션·한계 | 현재 weighted ordinary net으로 조용히 축소하지 않는다. Guard 표현은 별도 검증 가능한 식 계약이 필요하다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/petri_net/obj.py :: ResetNet`
- `pm4py/objects/petri_net/obj.py :: InhibitorNet`
- `pm4py/objects/petri_net/obj.py :: ResetInhibitorNet`
- `pm4py/objects/petri_net/inhibitor_reset/semantics.py :: execute`
- `pm4py/objects/petri_net/data_petri_nets/semantics.py :: is_enabled`
- `pm4py/objects/petri_net/data_petri_nets/semantics.py :: execute`
- `pm4py/convert.py :: convert_petri_net_type`

## PM-MODEL-003

**확률 전이와 분포를 가진 Petri net을 표현할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Place·arc·확률 전이 속성과 사용할 분포/가중치 정의. |
| 확인할 출력 | 확률적 실행 정보를 담아 계산에 전달할 stochastic Petri net 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Stochastic transition/분포/weight와 serialization·실행 capability를 모델 계약으로 추가한다. |
| 다음 작업 ID | MODEL-01, MODEL-02 |
| 의미·옵션·한계 | 여기서는 모델 표현만 소유한다. Playout·random-variable 학습·simulation 알고리즘은 고급 계산 행에 연결한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/petri_net/stochastic/obj.py :: StochasticPetriNet`

## PM-MODEL-004

**Tree·BPMN·POWL·Heuristics net·TS·trie 모델을 식별하고 읽을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 각 모델의 노드·관계·연산자·경계 및 모델별 필수 속성. |
| 확인할 출력 | 종류별 의미를 유지한 tree/BPMN/POWL/Heuristics net/TS/trie/GeneticMatrix 표현. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 기존 PIX tree 외 BPMN gateway/event·POWL strict partial order·Heuristics bindings·TS state·trie 종료·GeneticMatrix의 의미와 능력표를 추가한다. |
| 다음 작업 ID | MODEL-01, MODEL-02 |
| 의미·옵션·한계 | 서로 다른 모델 종류를 하나의 일반 graph로 취급하지 않는다. Pure representation 행이며 각 발견/변환 계산과 중복 구현하지 않는다. |

**현재 PIX 근거:** `ProcessTree`.
소스: [src/pix/contracts/discovery.py](../../../src/pix/contracts/discovery.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/process_tree/obj.py :: ProcessTree`
- `pm4py/objects/bpmn/obj.py :: BPMN`
- `pm4py/objects/powl/obj.py :: POWL`
- `pm4py/objects/heuristics_net/obj.py :: HeuristicsNet`
- `pm4py/objects/transition_system/obj.py :: TransitionSystem`
- `pm4py/objects/trie/obj.py :: Trie`
- `pm4py/objects/genetic_matrix/obj.py :: GeneticMatrix`

## PM-MODEL-005

**Process tree를 실행 가능한 Petri net으로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Process tree와 ordinary 또는 transition-bordered 변환 선택. |
| 확인할 출력 | Tree 실행을 표현하는 Petri net 및 초기/최종 marking. |
| 현재 PIX | 부분 대응 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | 기존 ordinary workflow-net 변환의 지원 operator를 검증하고 transition-bordered 변형의 경계·marking 의미를 추가한다. |
| 다음 작업 ID | MODEL-04 |
| 의미·옵션·한계 | PIX의 sequence/XOR/parallel/loop/tau tree→net 조합은 실제 구현이다. 참조 transition-bordered 구조 동일성까지 완료된 것은 아니다. |

**현재 PIX 근거:** `process_tree_to_petri_net`.
소스: [src/pix/compute/discovery.py](../../../src/pix/compute/discovery.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_petri_net`
- `pm4py/objects/conversion/process_tree/converter.py :: apply`
- 변형 `pm4py/objects/conversion/process_tree/converter.py :: Variants` → `TO_PETRI_NET`, `TO_PETRI_NET_TRANSITION_BORDERED`

## PM-MODEL-006

**Process tree를 BPMN 또는 POWL로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Process tree와 BPMN 또는 POWL 목표 모델 종류. |
| 확인할 출력 | Tree 연산을 해당 gateway 또는 부분순서 구조로 표현한 목표 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Operator별 BPMN gateway/POWL 관계와 silent·loop·boundary 의미를 보존하는 변환을 구현한다. |
| 다음 작업 ID | MODEL-02, MODEL-04 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_bpmn`
- `pm4py/convert.py :: convert_to_powl`
- `pm4py/objects/conversion/process_tree/converter.py :: apply`
- 변형 `pm4py/objects/conversion/process_tree/converter.py :: Variants` → `TO_BPMN`, `TO_POWL`

## PM-MODEL-007

**BPMN을 Petri net으로 변환하여 계산할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 지원하는 task·event·gateway·flow를 포함한 BPMN 모델. |
| 확인할 출력 | BPMN 실행 의미를 표현하는 Petri net과 초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 지원 event/task/gateway 조합·inclusive semantics·source/target marking과 미지원 BPMN 요소 손실을 명시한다. |
| 다음 작업 ID | MODEL-02, MODEL-04 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_petri_net`
- `pm4py/objects/conversion/bpmn/converter.py :: apply`
- 변형 `pm4py/objects/conversion/bpmn/converter.py :: Variants` → `TO_PETRI_NET`

## PM-MODEL-008

**Workflow net을 process tree 또는 BPMN으로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Workflow Petri net·초기/최종 marking과 tree/BPMN 목표 선택. |
| 확인할 출력 | 변환 가능한 구조의 process tree 또는 BPMN, 불가능할 때의 실패 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 변환 가능한 WF 구조 탐지·축약·도출 근거와 표현 불가능한 모델의 거절/한계를 구현한다. |
| 다음 작업 ID | MODEL-04, MODEL-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_process_tree`
- `pm4py/convert.py :: convert_to_bpmn`
- `pm4py/objects/conversion/wf_net/converter.py :: apply`
- 변형 `pm4py/objects/conversion/wf_net/converter.py :: Variants` → `TO_PROCESS_TREE`, `TO_BPMN`

## PM-MODEL-009

**Petri net 또는 BPMN을 POWL로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Workflow Petri net 또는 BPMN과 변환에 필요한 경계 정보. |
| 확인할 출력 | 분해 가능한 구조를 POWL로 표현한 모델 또는 변환 실패 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | WF 검증·partial order/loop/XOR 분해와 실패 witness를 구현하고 BPMN→net 경로 provenance를 유지한다. |
| 다음 작업 ID | MODEL-04, MODEL-05 |
| 의미·옵션·한계 | 최신 wheel에는 직접 호출되는 to_powl variant가 있지만 wf_net converter.Variants에는 등록되지 않는다. Enum만 검사하면 누락된다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_powl`
- `pm4py/objects/conversion/wf_net/variants/to_powl.py :: apply`

## PM-MODEL-010

**POWL을 net 또는 tree로 바꾸면 어떤 행동이 보존되는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | POWL 모델과 Petri net 또는 process tree 목표 선택. |
| 확인할 출력 | 목표 모델과 net인 경우 초기/최종 marking, 해당 변환의 의미 보존 범위. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | POWL→net과 POWL→tree의 부분순서 변환·근사/손실 가능성을 각각 검증하고 범위를 명시한다. |
| 다음 작업 ID | MODEL-04 |
| 의미·옵션·한계 | to_process_tree는 converter Enum 외 facade 직접 호출 경로이다. 일반 partial order와 block tree의 언어가 항상 동일하다고 가정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_petri_net`
- `pm4py/convert.py :: convert_to_process_tree`
- `pm4py/objects/conversion/powl/converter.py :: apply`
- `pm4py/objects/conversion/powl/variants/to_process_tree.py :: apply`
- 변형 `pm4py/objects/conversion/powl/converter.py :: Variants` → `TO_PETRI_NET`

## PM-MODEL-011

**Heuristics net·GeneticMatrix·trie를 Petri net으로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Heuristics net·GeneticMatrix 또는 종료 정보가 있는 trie. |
| 확인할 출력 | 원본 모델의 결합·경계 의미를 표현한 Petri net과 초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 각 원본 모델의 결합·경계·종료·빈 trace 의미를 유지하는 방향별 변환을 구현한다. |
| 다음 작업 ID | MODEL-02, MODEL-04 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/conversion/heuristics_net/converter.py :: apply`
- `pm4py/objects/conversion/genetic_matrix/converter.py :: apply`
- `pm4py/objects/conversion/trie/converter.py :: apply`
- 변형 `pm4py/objects/conversion/heuristics_net/converter.py :: Variants` → `TO_PETRI_NET`
- 변형 `pm4py/objects/conversion/genetic_matrix/converter.py :: Variants` → `TO_PETRI_NET`
- 변형 `pm4py/objects/conversion/trie/converter.py :: Variants` → `TO_PETRI_NET`

## PM-MODEL-012

**DFG를 서로 다른 구조의 Petri net으로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | DFG·시작/종료 활동과 activity-place 또는 invisible 구성 선택. |
| 확인할 출력 | 선택한 구성 규칙의 Petri net과 초기/최종 marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Activity-place와 invisible/no-duplicate 구성의 차이·start/end·허용 언어를 구현한다. |
| 다음 작업 ID | MODEL-04 |
| 의미·옵션·한계 | 두 구조는 단순 layout 변경이 아니다. DFG→net 허용 언어를 일반 발견 miner와 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/conversion/dfg/converter.py :: apply`
- 변형 `pm4py/objects/conversion/dfg/converter.py :: Variants` → `VERSION_TO_PETRI_NET_ACTIVITY_DEFINES_PLACE`, `VERSION_TO_PETRI_NET_INVISIBLES_NO_DUPLICATES`

## PM-MODEL-013

**현재 marking에서 도달 가능한 전체 상태와 전이는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net·초기 marking과 상태/시간 탐색 한도. |
| 확인할 출력 | 도달 marking을 상태로 하는 graph·발화 edge와 탐색 완전성 정보. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Reachability graph를 독립 결과로 제공하고 상태/시간 한도·unbounded 후보·완전성·상태별 witness를 반환한다. |
| 다음 작업 ID | MODEL-05 |
| 의미·옵션·한계 | PIX 내부 bounded state search는 존재하나 전체 reachability 분석 API나 완전성 증명을 대신하지 않는다. |

**현재 PIX 근거:** `fire`, `enabled_transitions`, `align_traces`.
소스: [src/pix/compute/model_semantics.py](../../../src/pix/compute/model_semantics.py), [src/pix/compute/conformance.py](../../../src/pix/compute/conformance.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_reachability_graph`
- `pm4py/objects/petri_net/utils/reachability_graph.py :: construct_reachability_graph`
- `pm4py/objects/petri_net/utils/reachability_graph.py :: marking_flow_petri`

## PM-MODEL-014

**모델이 workflow-net 구조 조건을 만족하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Place·transition·arc로 구성한 Petri net. |
| 확인할 출력 | Unique source/sink와 경로 포함 조건에 따른 workflow-net 판정. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Unique source/sink·모든 노드의 경로 포함 등 WF-net 구조 조건과 반례를 구현한다. |
| 다음 작업 ID | MODEL-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: check_is_workflow_net`
- `pm4py/algo/analysis/workflow_net/algorithm.py :: apply`
- 변형 `pm4py/algo/analysis/workflow_net/algorithm.py :: Variants` → `PETRI_NET`

## PM-MODEL-015

**Workflow net은 종료 가능성·dead transition·boundedness 등 soundness를 만족하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Workflow 후보 Petri net·초기/최종 marking과 분석 한도. |
| 확인할 출력 | Soundness 판정 및 boundedness·liveness·dead transition 등의 진단/반례. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | S-components/invariants·coverability/reachability·boundedness·liveness·soundness 증명/반례/unknown을 구현한다. |
| 다음 작업 ID | MODEL-05 |
| 의미·옵션·한계 | 관측 trace를 수용하거나 OCPN joint witness가 있다는 사실은 일반 soundness 증명이 아니다. check_is_sound의 POWL 변환 shortcut도 정의/보장 검토 대상으로 포함한다. 추가로 연결한 entry/helper는 입력 표현·병렬 실행·진단 또는 동일 알고리즘 내부 단계이며 독립 계산군으로 중복 계수하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: check_soundness`
- `pm4py/analysis.py :: check_is_sound`
- `pm4py/algo/analysis/woflan/algorithm.py :: apply`
- `pm4py/algo/analysis/woflan/algorithm.py :: compute_non_live_sequences`
- `pm4py/algo/analysis/woflan/algorithm.py :: compute_unbounded_sequences`
- `pm4py/algo/analysis/woflan/algorithm.py :: short_circuit_petri_net`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_1`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_2`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_3`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_4`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_5`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_6`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_7`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_8`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_9`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_10`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_11`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_12`
- `pm4py/algo/analysis/woflan/algorithm.py :: step_13`

## PM-MODEL-016

**Marking equation으로 도달 비용 하한을 계산할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net·초기/최종 marking·전이 비용과 LP/ILP 설정. |
| 확인할 출력 | Marking equation 최적 목적값인 비용 하한과 solver 해/실패 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Incidence·cost·LP/ILP equation과 해·infeasible·하한 의미를 구현한다. |
| 다음 작업 ID | MODEL-05, CONF-05 |
| 의미·옵션·한계 | Equation 해 존재는 일반 reachability 증명이 아니다. LP solver는 수치 backend 경계로 둔다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: solve_marking_equation`
- `pm4py/algo/analysis/marking_equation/algorithm.py :: build`
- `pm4py/algo/analysis/marking_equation/algorithm.py :: get_h_value`
- 변형 `pm4py/algo/analysis/marking_equation/algorithm.py :: Variants` → `CLASSIC`

## PM-MODEL-017

**Split point를 가진 extended marking equation 하한은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace·synchronous-product net·초기/최종 marking과 split point·비용. |
| 확인할 출력 | 중간 제약을 반영한 extended marking equation 비용 하한과 해 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Trace 분할·중간 marking 제약·목적함수·하한 조건을 기본 marking equation과 분리 구현한다. |
| 다음 작업 ID | MODEL-05, CONF-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: solve_extended_marking_equation`
- `pm4py/algo/analysis/extended_marking_equation/algorithm.py :: build`
- `pm4py/algo/analysis/extended_marking_equation/algorithm.py :: get_h_value`
- 변형 `pm4py/algo/analysis/extended_marking_equation/algorithm.py :: Variants` → `CLASSIC`

## PM-MODEL-018

**Trace와 모델의 synchronous product를 구성할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Trace·Petri net·초기/최종 marking과 선택적인 이동별 비용. |
| 확인할 출력 | Log/model/synchronous 전이를 구분한 product net·초기/최종 marking 및 비용 대응. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Log/model/synchronous 전이와 cost-aware product를 명시 모델로 제공하고 source mapping을 유지한다. |
| 다음 작업 ID | MODEL-04, CONF-05 |
| 의미·옵션·한계 | PIX은 product 상태를 직접 탐색한다. 명시 synchronous-product net 생성/교환 API는 없다. |

**현재 PIX 근거:** `align_traces`.
소스: [src/pix/compute/conformance.py](../../../src/pix/compute/conformance.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: construct_synchronous_product_net`
- `pm4py/objects/petri_net/utils/synchronous_product.py :: construct`
- `pm4py/objects/petri_net/utils/synchronous_product.py :: construct_cost_aware`

## PM-MODEL-019

**모델을 최대 구성요소로 분해하고 다시 조합할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Accepting Petri net 또는 병합할 부분 net과 marking. |
| 확인할 출력 | 최대 분해 구성요소 목록 또는 재조합한 net·marking. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Invisible/동일 label 공유 기준·marking 투영·재조합과 노드 대응을 구현한다. |
| 다음 작업 ID | MODEL-06, CONF-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: maximal_decomposition`
- `pm4py/objects/petri_net/utils/decomposition.py :: decompose`
- `pm4py/objects/petri_net/utils/decomposition.py :: merge_comp`
- `pm4py/objects/petri_net/utils/decomposition.py :: merge_sublist_nets`

## PM-MODEL-020

**불필요한 invisible 구조나 implicit place를 의미를 보존하며 제거할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 지원하는 ordinary/reset/inhibitor net·marking과 reduction 규칙 선택. |
| 확인할 출력 | 선택한 보존 조건에서 축약한 net·marking 및 원본 구조 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Ordinary silent reduction·Murata implicit-place·reset/inhibitor별 규칙의 전제·보존 관계·원본 대응을 구현한다. |
| 다음 작업 ID | MODEL-06, MODEL-05 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: reduce_petri_net_invisibles`
- `pm4py/analysis.py :: reduce_petri_net_implicit_places`
- `pm4py/objects/petri_net/utils/reduction.py :: apply_simple_reduction`
- `pm4py/objects/petri_net/utils/murata.py :: apply_reduction`
- `pm4py/objects/petri_net/utils/reduction.py :: apply_reset_inhibitor_net_reduction`

## PM-MODEL-021

**모델을 graph로 전달하고 활동 label을 읽거나 바꿀 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Petri net 또는 지원 모델과 graph 투영/label 조회·치환 요청. |
| 확인할 출력 | Graph 표현·활동 label 목록 또는 label을 치환한 모델. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Model graph projection·node identity·label 변경 provenance를 모델 종류별 구현한다. |
| 다음 작업 ID | MODEL-02, MODEL-04 |
| 의미·옵션·한계 | 현재 PIX graph view와 직접 NetworkX 객체 교환은 별개다. NetworkX 반환 타입 그대로의 호환은 계산 대체의 자동 요건으로 확정하지 않는다. |

**현재 PIX 근거:** `build_model_graph`.
소스: [src/pix/viewer/model_adapter.py](../../../src/pix/viewer/model_adapter.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_petri_net_to_networkx`
- `pm4py/analysis.py :: get_activity_labels`
- `pm4py/analysis.py :: replace_activity_labels`

## PM-MODEL-022

**두 모델이 행동·구조 관점에서 얼마나 비슷한가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 비교 가능한 모델 두 개와 행동/구조 유사도 선택. |
| 확인할 출력 | Footprints 또는 tree 구조에 근거한 모델 간 유사도 점수. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Footprint sequence/parallel 유사도와 process-tree structural 유사도를 별도 지표로 구현한다. |
| 다음 작업 ID | MODEL-05, DISC-06 |
| 의미·옵션·한계 | 유사도 점수가 언어 동치 증명이나 conformance fitness를 뜻하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: behavioral_similarity`
- `pm4py/analysis.py :: structural_similarity`

## PM-MODEL-023

**모델 embedding 또는 label 의미로 유사도와 label 매핑을 구할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 모델 두 개·label 집합과 embedding/문자열 유사도·threshold 설정. |
| 확인할 출력 | Embedding/label 유사도 또는 대응 label로 변경한 모델과 매핑. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Embedding/문자열 유사도 backend·threshold·matching 방향·seed·지원 모델을 고정하고 label mapping 근거를 반환한다. |
| 다음 작업 ID | MODEL-05, MODEL-04 |
| 의미·옵션·한계 | 외부 embedding 의존성/모델 선택은 계산 backend 정책으로 명시하고 native deterministic structural 계산과 구분한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: embeddings_similarity`
- `pm4py/analysis.py :: label_sets_similarity`
- `pm4py/analysis.py :: map_labels_from_second_model`

## PM-MODEL-024

**지정 trace 분석에 불필요한 선택적 tree 부분을 줄일 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Process tree·비교할 단일 trace와 활동 classifier. |
| 확인할 출력 | 해당 trace와 겹치지 않는 skippable 부분을 tau로 치환하고 접은 process tree. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Trace별 footprint·skippability 조건과 tau 치환·fold를 구현하고 해당 분석에서 보존해야 할 비용/행동 조건을 검산한다. |
| 다음 작업 ID | MODEL-06, CONF-05 |
| 의미·옵션·한계 | 지정 trace에 대한 축약이다. 원본 전체 모델 언어를 항상 보존하는 일반 reduction으로 표시하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/reduction/process_tree/reducer.py :: apply`
- `pm4py/algo/reduction/process_tree/variants/tree_tr_based.py :: apply`
- `pm4py/algo/reduction/process_tree/variants/tree_tr_based.py :: reduce`
- 변형 `pm4py/algo/reduction/process_tree/reducer.py :: Variants` → `TREE_TR_BASED`

## PM-MODEL-025

**입출력 marker group·cardinality로 객체 중심 causal net을 만들고 상태를 해석할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동별 입출력 marker group·객체 유형·최소/최대 참여 수·공유 marker key와 의무 상태. |
| 확인할 출력 | OCCausalNet 모델과 outstanding obligation의 소비·생성에 따른 실행 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Marker/key/cardinality·의무 상태·binding·발화 의미를 구현하고 factory의 정보 범위를 명시한다. |
| 다음 작업 ID | MODEL-01, MODEL-02 |
| 의미·옵션·한계 | 참조 factory는 activity count·relative occurrence threshold를 고려하지 않으며 입력을 변경할 수 있다. PIX에서 이 부작용까지 복제할 요구는 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/oc_causal_net/obj.py :: OCCausalNet`
- `pm4py/objects/oc_causal_net/creation/factory.py :: create_oc_causal_net`
- `pm4py/objects/oc_causal_net/semantics.py :: OCCausalNetState`
- `pm4py/objects/oc_causal_net/semantics.py :: OCCausalNetSemantics`

## PM-MODEL-026

**객체 token과 variable arc를 가진 OCPN을 구성하고 발화할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Typed place·전이·variable/fixed arc·객체별 초기/최종 marking 또는 type별 net이 있는 발견 사전. |
| 확인할 출력 | 객체 ID를 유지한 OCPN과 binding의 enable·발화 후 marking. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PM4Py 객체 binding·variable cardinality·factory marking 정책과 PIX finite-object 의미를 대조하고 legacy 발견 사전 입력 매핑을 추가한다. |
| 다음 작업 ID | MODEL-01, MODEL-02, OCONF-01 |
| 의미·옵션·한계 | PIX의 concrete-object OCPN 발화가 존재한다. 참조 factory는 activities/petri_nets/double_arcs_on_activity/object_ids만 고려하므로 그 외 정보 보존을 별도로 검증해야 한다. |

**현재 PIX 근거:** `ObjectCentricPetriNet`, `ObjectMarking`, `is_binding_enabled`, `fire_binding`.
소스: [src/pix/contracts/models.py](../../../src/pix/contracts/models.py), [src/pix/compute/model_semantics.py](../../../src/pix/compute/model_semantics.py).
실행 기록: [E-MODEL](../../../docs/version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/ocpn/obj.py :: OCPetriNet`
- `pm4py/objects/ocpn/obj.py :: OCMarking`
- `pm4py/objects/ocpn/factory.py :: create`
- `pm4py/objects/ocpn/semantics.py :: OCPetriNetSemantics`

## PM-MODEL-027

**OCCausalNet을 OCPN으로 변환하면 어떤 제약이 유지되거나 손실되는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 입출력 marker group·key·참여 수 범위가 있는 OCCausalNet. |
| 확인할 출력 | Marker 구조를 Petri net으로 옮긴 OCPN과 cardinality/key/marking 손실 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Marker/key group 변환과 cardinality 표현 능력을 검토하고 수용 의미가 넓어지는 부분·초기/최종 상태 미설정을 보고한다. |
| 다음 작업 ID | MODEL-04, MODEL-01 |
| 의미·옵션·한계 | 고정 참조 구현은 빈 markings, (1,1) 외 cardinality를 (0,*)로 취급, input marker key 무시를 명시한다. 손실 없는 동치 변환으로 묶지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/oc_causal_net/converter.py :: apply`
- `pm4py/objects/oc_causal_net/variants/to_ocpn.py :: apply`
- 변형 `pm4py/objects/oc_causal_net/converter.py :: Variants` → `TO_OCPN`

## PM-MODEL-028

**OCPN의 객체 흐름을 marker 기반 causal net으로 표현할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Object-centric Petri net의 typed place·arc·전이와 초기/최종 marking. |
| 확인할 출력 | Auxiliary 활동·type별 START/END·입출력 marker group을 가진 OCCausalNet. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Transition/place 의존·variable type·시작/종료 marker 변환을 구현하고 원본 요소 대응과 추가 auxiliary 활동을 추적한다. |
| 다음 작업 ID | MODEL-04 |
| 의미·옵션·한계 | 이 방향의 변환과 OCCN→OCPN 방향의 보존 조건은 별도로 검증한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/ocpn/converter.py :: apply`
- `pm4py/objects/ocpn/variants/to_oc_causal_net.py :: apply`
- 변형 `pm4py/objects/ocpn/converter.py :: Variants` → `TO_OC_CAUSAL_NET`

## PM-MODEL-029

**OCPN을 type별 Petri net 중심의 발견 결과 표현으로 바꿀 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 객체 중심 Petri net과 초기/최종 객체 marking. |
| 확인할 출력 | Type별 Petri net·marking, 활동·variable arc·시작/종료 정보가 있는 대체 형식 사전. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Type projection·marking 집계·variable arc 정보 매핑을 구현하고 원본 객체 ID/다중도 보존 범위를 표시한다. |
| 다음 작업 ID | MODEL-04, MODEL-06 |
| 의미·옵션·한계 | 참조는 standalone 모델에 없는 edge/performance/activity 관측 통계를 빈 집합/사전으로 채운다. 이 값을 실제 계산된 0이나 관측 없음의 증거로 해석하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/ocpn/converter.py :: apply`
- `pm4py/objects/ocpn/variants/to_alternative_format.py :: apply`
- 변형 `pm4py/objects/ocpn/converter.py :: Variants` → `TO_ALTERNATIVE_FORMAT`
