# 모델과 W4 계산 사용 가이드

작업 시작일: 2026-09-17. 문서 검토일: 2026-09-18. 이번 구현의 범위·반례·검증 근거는
[구현 보고서](../reports/2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md)에 있다.
이 가이드는 계산을 연결할 때 필요한 도메인 선택과 결과 해석을 설명한다.

## 모델에서 시작할 때

첫 단계는 모델 종류와 필요한 계산을 함께 고르는 것이다. Native JSON에 저장할 수 있는 모델이라고 해서
모든 alignment·reachability가 가능하지는 않다. [Capability API](../../src/pix/model_capabilities.py)의
직접 지원, 명시 변환 후 지원, 미지원 구분을 먼저 확인한다.

외부 모델은 `pix.model_io`의 `read_pnml`, `read_ptml`, `read_bpmn`으로 읽는다.
반환된 `ParsedModel.model`이 계산 입력이고, wrapper에는 교환 관련 근거가 남는다.
출력은 같은 모듈의 `write_*`를 사용한다. 기본 저장 정책은 기존 파일 보호이며, 교체가 필요할 때만
`overwrite=True`를 지정한다. PNML의 최종 marking을 sink에서 추측하거나 BPMN의 미지원 요소를 지워 읽지 않는다.
현재 BPMN reader는 DI(화면 배치 정보)도 거부하므로, 일반 편집기가 출력한 모든 BPMN 파일을 바로 읽는다고
가정하지 않는다. 허용 profile과 오류의 요소 이름을 먼저 확인한다.

| 하고 싶은 일 | 사용할 계산 | 선택해야 하는 의미 |
|---|---|---|
| POWL을 tree로 바꾸기 | `powl_to_process_tree` | Occurrence를 복제하지 않는 series/parallel 구조. N형 순서는 거부 |
| 관측 trie를 수락 모델로 바꾸기 | `trie_to_petri_net` | 명시 terminal prefix만 종료 허용. 빈 모집단과 empty trace 구분 |
| Tree의 각 하위 구조 경계를 전이로 표현 | `tree_to_transition_bordered_petri_net` | Sequence·XOR·parallel·binary loop, tau와 occurrence 경계 유지 |
| PN 구성요소 분해/재결합 | `maximal_decompose_model`, `recompose_maximal_decomposition` | Shared transition은 원본 ID로 동기화. 독립 실행의 단순 합 아님 |
| Token 무한 증가/coverability 검사 | `coverability` | Weighted ordinary P/T. Omega와 실제 marking, partial과 증명을 구분 |
| 객체형의 특정 업무구간 조사 | `local_ocpn_subprocess`, `transform_ocpn_subprocess` | 잘린 다른 객체형의 동기화와 marking 손실을 확인 |
| 모델 활동명 읽기/바꾸기 | `activity_labels`, `rename_activity_labels` | 같은 label의 서로 다른 occurrence는 그대로 유지 |

Reset/inhibitor 모델은 별도 자료형·발화 API를 사용한다. Inhibitor threshold는 발화 전 token 수의
엄격한 상한이고 reset은 해당 place의 모든 token을 지운다. Stochastic 모델은 모든 전이의 상대 weight와
duration 분포를 요구하며, 각 파라미터 출처를 따로 받는다. Ordinary PN 연산에 wrapper를 벗겨 전달하면
다른 문제를 푸는 것이므로 그렇게 지원 범위를 우회하지 않는다.

## Case 데이터로 예측용 표본을 만들 때

계산 순서는 **관측시점 선택 → follow-up·완료 근거 연결 → 그룹/시간 분할 → train encoder 학습 → 변환**이다.

1. `observation_dataset`에 관측시점을 지정한다. 입력은 그 시점까지의 event이고 이후 event는 target 쪽이다.
2. `CaseFollowUp`으로 어디까지 추적했고 언제 완료를 관측했는지 선언한다. 기록의 끝을 완료로 쓰지 않는다.
3. `leakage_safe_split`으로 같은 case/공유 그룹을 같은 partition에 둔다. 시간 분할에서 label이 늦게 확정된다면 `CaseAvailability`로 그 종료를 제공한다. 생략하면 event 구간만 사용한다.
4. `fit_observation_encoder`는 training case만 본다. `transform_observations`에서 test의 새 범주는 unknown이다.
5. Sequence가 필요하면 `encode_case_sequences`를 사용한다. Padding과 결측 mask, 실제 0, 잘린 event ID를 함께 유지한다.

`A@0 → B@5 → C@9`를 B 직후 예측하는 예에서 event 수 2와 경과 5는 입력이다.
완료 근거가 9에 있으면 remaining 4는 정답이다. C를 미래 정보로 입력에 섞으면 계산은 빨라도 평가가 무효해진다.
‘완료 관측’, ‘우측 검열’, ‘horizon까지 미완료’를 한 label로 합치지 않는다.

관련 API: [feature_dataset](../../src/pix/case_centric/feature_dataset.py).

## Object-centric 표본을 만들 때

OC feature 결과에서 `build_object_k_step_dataset`으로 시간창을 만든다. Timestamp와 execution identity가
있는 행이 대상이며 그 정보가 없는 행은 제외된다. 모든 feature granularity가 자동으로 시간창이 되는 것은 아니다.
K는 서로 다른 timestamp 묶음 수다. 동시각 event를 ID순으로 펼쳐 가짜 선후관계를 만들지 않는다.
각 표본의 execution/event/object membership과 partition을 유지해야 공유 객체를 통한 누출을 검사할 수 있다.

`fit_object_regression`은 native 선형 최소제곱 baseline을 만든다. `predict_object_regression`은 고정된 모델로
예측하고 `evaluate_object_regression`은 분리된 표본의 target별 MAE를 계산한다. 학습에 사용한 표본에 대한
진단용 예측과 held-out 성능을 구별한다. Rank 부족·결측 제외·실제 평가 쌍 수를 확인한 뒤 MAE를 읽는다.

`inverse_transform_object_features`는 encoder의 학습 통계를 이용해 값을 원래 단위로 되돌린다.
Unknown 범주·모호한 one-hot·복원할 수 없는 셀은 복원된 값처럼 채우지 않는다.
부동소수점 수치 변환이므로 큰 정수의 bit 단위 무손실 복원까지 보장하지 않는다.
외부에서 만든 feature가 과거 시점에 실제 가용했는지는 이 모듈만으로 증명되지 않는다.

관련 API: [learning](../../src/pix/object_centric/learning.py).

## Decision과 drift를 평가할 때

`evaluate_decision_table`은 기존 conformance 기반 분기 표본에 연결한다.
외부의 분기 feature/label 자료에는 `evaluate_decision_tree`를 사용할 수 있으나 feature 가용시점의 근거가 필요하다.
Training/test case와 공유 그룹, label 확정 여부를 먼저 확인한다.
Unknown/missing으로 제외된 occurrence가 있으면 ‘채점한 표본의 정확도’와 전체 coverage를 따로 읽는다.
상위 분기 표본이 한도로 잘렸다면 전체 coverage는 알 수 없음이다. Conformance adapter는 기존 수치
feature를 연결하며 범주형 feature를 분기 직전 기록에서 자동 추출하는 기능은 별도다.

`adjust_drift_pvalues`에는 기존 Bose drift 결과 전체를 전달한다. 기본 Holm은 계획한 모든 window를
검정군으로 삼는다. BH를 선택하면 의존성 조건을 추가로 검토해야 한다. 그림에 표시된 peak만 보정하면
실제로 수행한 여러 검정을 숨기게 된다.
미완료 family의 보수적 상한은 완성된 adjusted p-value가 아니다. `rejected=None`은 ‘변화 없음’이 아니다.

관련 API: [decision_evaluation](../../src/pix/case_centric/decision_evaluation.py),
[drift_evaluation](../../src/pix/case_centric/drift_evaluation.py).

## Simulation에서 먼저 고를 가정

| 계산 | 적합한 질문 | 반드시 함께 읽을 것 |
|---|---|---|
| `playout_timed_petri_net` | Token 선후관계와 병렬 실행을 가진 모델의 시간이 어떻게 되는가? | 시작 token 예약, 완료 output, duration·weight 출처, 완료/진행 중/한도 종료 |
| `simulate_resources` | 도착한 case의 순차 작업이 capacity/calendar에서 얼마나 기다리는가? | 동일 자원 동시 요구량, 비선점 작업, 전체 작업이 들어갈 열린 구간, infeasible case |
| `compare_resource_scenarios` | 같은 모집단에서 capacity 등 가정을 바꾸면 무엇이 달라지는가? | 동일 cohort/horizon, 공통 난수, 양쪽 완료 case의 쌍과 완료 수 차이 |
| `fit_resource_durations` | Lifecycle로 관측한 service time에서 어떤 duration 파라미터를 얻는가? | 실제 service 근거, unmatched 기록, 가정한 분포 family |

순차 duration 2·3은 5, 자원 제약이 없는 독립 병렬 2·3은 3이어야 한다.
완료된 case만의 평균은 미완료 case가 포함된 전체 모집단의 평균이 아니다.
Horizon에 걸린 실행을 버리지 말고 예정 완료와 관측 완료를 구별한다.
시간은 profile에 명시한 초 단위이며, calendar는 유한 절대구간이다. 주간 반복·시간대 DST·선점은 별도 지원 범위다.
Lifecycle의 suspend/resume이 해결되지 않은 구간은 경과시간 전체를 service time으로 학습하지 않는다.
제외된 구간과 실제 fitting 표본을 먼저 확인한다.

관련 API: [timed_playout](../../src/pix/case_centric/timed_playout.py),
[resource_simulation](../../src/pix/case_centric/resource_simulation.py).

## Streaming 상태를 갱신할 때

Case는 `RevisableCaseStream`, OCEL은 `OCRevisableStream`을 사용한다.
수신 event ID와 source offset, 요청 operation ID를 유지한다. 같은 요청 재전송과 다른 내용의 정정을 구분한다.
Case의 event 정렬 profile은 명시하며 XES 기록 순서와 event-time 순서를 섞지 않는다.

정정/삭제 뒤 영수증의 revision과 철회/추가를 소비자에게 전달한다. OCEL에서는 E2O 변경 하나가
execution을 합치거나 나눌 수 있으므로 execution ID 집합만 교체하지 말고 변경 근거도 보존한다.
기존 개체 정정 시 현재 revision을 사용하고 충돌을 무조건 최신 값으로 덮지 않는다.
Case 정정은 해당 event의 revision, OC 정정은 stream 전체 revision을 검사한다. Case source offset은
선택 사항이며 source·partition별 증가 정수다. OC offset은 필수인 opaque token이고 순서를 가정하지 않는다.
두 계약을 transport adapter에서 같은 의미로 취급하지 않는다.

Checkpoint는 restore 후 operation replay 일관성을 검사한다. Source offset은 중복 식별자이며
watermark나 ‘이보다 이른 event는 절대로 안 온다’는 보증이 아니다. 현재 구현은 이력을 보존한 정확 재계산 경로다.
Kafka 운영, 분산 exactly-once, 무제한 입력의 일정 메모리 운용을 대신하지 않는다.

관련 API: [Case stream](../../src/pix/case_centric/revisable_stream.py),
[OC stream](../../src/pix/object_centric/revisable_stream.py).

## Action 계획을 Schumpeter에 넘길 때

`enumerate_action_matches`는 temporal pattern의 모든 발견 witness를 후보로 만든다.
같은 semantic action의 두 witness를 두 번의 실행으로 볼지, 서로 대체 가능한 후보로 볼지는 도메인 정책이다.
Alternative ID를 유지하고 그 정책을 conflict/required/optional 계약에 반영한다.

`plan_actions`에는 후보 전체의 required/optional 분류와 선후관계·충돌·release·deadline·비용·horizon을 전달한다.
목적함수를 지정하지 않으면 feasibility만 묻는다. `optimal`은 전달한 후보 집합과 지원 제약 안의 최적이다.
후보 열거가 partial이면 아직 발견되지 않은 후보까지 포함한 전역 최적이라고 확대하지 않는다.

No-op이 feasible인지 별도 확인한다. Required action이 있는데 빈 계획이 나오면 의무를 충족한 것이 아니다.
`infeasible`은 탐색 완주에 근거하고, 한도 때문에 아직 못 찾은 경우는 `unknown`이다.

`assess_operational_impact`는 동일한 모델·검증 replay의 두 event-prefix snapshot에서 객체 모집단 차이를
설명한다. Baseline/scenario 인자는 두 snapshot의 위치이며, 모델 변경을 적용하거나 서로 다른 모델의
반사실 실행을 만드는 인자가 아니다. Cutoff는 처리한 고유 event 수이며 timestamp가 아니다.
관측 binding·silent 추론·token 보정·unknown을 구분하고, 모든 marking을 모델에 조건부인 추론으로 읽는다.
별도의 관측 성능 비교에서 waiting 평균 10→8의 차이 −2를 얻어도 그 action 때문에 2만큼 개선됐다는
인과 주장이 되지는 않는다. PIX 결과는 실행 허가나 실제 도구 호출이 아니다.

관련 API: [action_planning](../../src/pix/object_centric/action_planning.py),
[operational_impact](../../src/pix/object_centric/operational_impact.py).

## 검토와 재현

[작은 수검산 예제](../../examples/models_w4_review.py)는 주요 계산을 실제 공개 API로 연결한다.
개별 입력을 바꾸기 전에는 보고서의 기대값을 확인하고, 바꾼 뒤에는 값뿐 아니라 상태·근거·제외 모집단을 비교한다.
결과 JSON에는 source/profile/부모 계산을 함께 보존한다. 그래프의 모양이 같아도 이들이 다르면 같은 판단이 아니다.

추가된 범위의 구조 연결은 `python tools/check_models_w4_registry.py`로 확인한다.
과거 inventory의 strict hash를 현재 소스에 맞춰 다시 쓰는 검사가 아니다. 최종 테스트와 설치 검증 결과는
위 구현 보고서에서 확인한다.

이 가이드의 지원 판단은 명시한 코드와 profile에 유효하다. 독립 반례로 발화·언어·cutoff·분모·최적성·정정·저장
계약이 깨지면 해당 판단을 철회하고 수정한다. 운영 규모 성능과 예측/행동 성공률은 별도 측정 전 **알 수 없음**이다.
