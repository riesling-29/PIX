# PIX Native Process Mining 합집합 구현 구조

작성일: 2026-09-15. 근거: [고정 SCOPE-01 대체표](2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md),
[행별 실제 구현 registry](union-2026-09-15/implementation_registry.json), 현재 소스와 해당 테스트.
목표는 PM4Py·OCPA 계산을 PIX에서 직접 수행하는 것이며, 참조 패키지의 함수를 실행하는 wrapper는 대체 구현으로 인정하지 않는다.

도메인 검토용 행별 설명은 [Case-Centric 대응표](union-2026-09-15/CASE_CENTRIC_COVERAGE.md)와
[Object-Centric 대응표](union-2026-09-15/OBJECT_CENTRIC_COVERAGE.md)에 나누었다.
[사용 예](../user-guide/NATIVE_MINING_GUIDE.md)와
[최종 검증 기록](../version/2026-09-15_NATIVE_MINING_VALIDATION.md)도 별도로 제공한다.

## 1. 범위와 읽는 방법

2026-09-18 추가 모델·W4 구현은 [후속 보고서](../reports/2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md)와
[추가 registry](models-w4-2026-09-17/implementation_registry.json)에 기록한다.
이 문서와 9월 15일 registry의 수치·source hash는 당시 snapshot을 유지하며,
새 구현이 모든 참조 variant의 대체 검증 완료를 뜻하지 않는다.

고정한 PM4Py 2.7.23.8·OCPA 1.3.4의 334개 검토 행 중 계산 및 필수 계산 지원에 해당하는
268개 행을 83개 구현 패키지에 연결했다. Case-Centric은 51개 패키지·168개 행,
Object-Centric은 32개 패키지·100개 행이다. 나머지 66개 행은 파일 입출력·렌더링·외부 서비스 연결
등으로 기존 제품 범위에 남아 있다. 계산 합집합에서 제외했다고 제품 개발 계획에서 삭제한 것은 아니다.

**패키지 수·행 수·함수 수는 알고리즘 수나 완성률이 아니다.** 하나의 행이 여러 알고리즘을 묶기도 하고,
서로 다른 상위 함수가 같은 계산을 호출하기도 한다. 합집합은 같은 업무 질문을 한 곳에서 관리한다는
뜻이며, 서로 다른 계산 정의를 같은 이름으로 합친다는 뜻은 아니다.

| Registry 상태 | 의미 | 이 상태만으로 주장하지 않는 것 |
|---|---|---|
| `native_profile` | 명시된 PIX 정의를 실제 코드로 계산하는 경로가 있다 | 모든 참조 variant와의 수치·구조 동등성 |
| `partial` | 해당 행의 일부 정의·입력·변형에 대응하는 계산 또는 재사용 가능한 부분이 있다 | 행 전체 대체 완료 |
| `unimplemented` | 행의 대응 계산 경로가 없다 | 비슷한 결과가 다른 함수에 있다는 이유로 지원 인정 |
| `external_runtime_unverified` | 코드·계약은 있지만 필요한 외부 수치/학습 runtime을 통한 실행 근거가 아직 부족하다 | 실제 학습 모델·solver를 실행했다는 주장 |

`reference_replacement_verified`와 위 구현 상태는 별개다. 기존 코드가 실행되거나 테스트 파일이
있다는 사실만으로 참조 대체 검증을 완료 처리하지 않는다. Registry의 `actual`은 현재 함수와 테스트를,
`planned_public_functions`는 이전 설계상의 이름을 기록한다. 둘은 혼용하지 않는다.

현재 분류는 `native_profile` 126행, `partial` 141행, `external_runtime_unverified` 1행이다.
268행 모두 실제 계산 또는 부분 지원 경로에 연결되었지만, 한 행 안의 잔여 variant가 사라졌다는
뜻은 아니다. 참조 전체 대체 검증이 끝난 행은 아직 0행으로 기록한다.

## 2. Case-Centric과 Object-Centric의 경계

공개 진입점은 `pix.case_centric`과 `pix.object_centric`으로 구분한다.

- Case-Centric은 `CaseLog` 또는 명시적으로 투영한 case 활동열을 받는다. 기본 활동 순서는 원본 기록 순서다.
- Object-Centric은 canonical OCEL의 event·object·E2O/O2O·qualifier·객체 속성 이력을 받는다.
  하나의 event가 여러 object에 참여한다는 사실을 계산 중 보존한다.
- 객체형 하나를 case로 펼치는 분석은 명시적 projection이다. 그 결과의 replay는 공동 객체 모델의
  joint replay/alignment와 다른 계산이다.
- 두 `CaseLog`의 연결·interleaving 분석에서 OCEL을 만드는 경로도 별도 bridge다.
  이 계산은 case namespace에서 시작하며 유도한 객체 관계를 원본 OCEL 관측과 구별한다.
- 최단 경로, 집계, 구간 비교, 행렬·정수 최적화 같은 내부 연산은 입력 의미가 같을 때 공유한다.
  Case 순서와 객체 간 부분순서가 다르면 같은 내부 함수에 암묵적으로 넣지 않는다.
- 결과에는 source/model/profile·선택 범위·witness·한도·unknown coverage를 남긴다.
  `computed`는 선택한 정의의 계산 완료를 뜻하며 업무 규범의 정당성이나 미래 성공을 뜻하지 않는다.

## 3. Case-Centric 계산 구조

아래 표는 사용자가 판단할 계산군이다. 정확한 행별 함수와 남은 variant는 registry에 연결되어 있다.

| 계산군 | 실제 코드가 다루는 내용 | 구분해서 검토할 정의 |
|---|---|---|
| IM·IMf·IMd | 가중 trace cut, 빈도 DFG filtering, DFG만으로 하는 재귀 발견 | IMf를 낮은 빈도 variant 삭제로 대체하지 않음. Plain sequence와 참조 strict optional-block merging 차이 |
| Alpha·Alpha+ | 인과 maximal pair, 길이 1/2 loop와 loop context 복원 | Formal exact context와 참조 subset attachment, epsilon·불완전 loop 관측 |
| Heuristics·Heuristics++ | dependency·short loop·AND relation·binding, 명시 구간 overlap | Classic/++ 수식·threshold 부등호·strict/closed interval 경계, net 변환의 지원 범위 |
| Region·Genetic·POWL·Split | 각기 다른 후보 공간과 실제 Petri net·POWL·BPMN 표현 | 유한 region 최적화와 참조 ILP formulation, GeneticMatrix와 finite-tree genotype, POWL 발견 variant, Split의 OR/SESE 처리 |
| 관계·상태 발견 | DFG/EFG, log footprint, transition system, prefix trie, batch, local process model | Event-position 빈도와 case-presence 빈도, 관측 대칭과 실제 병렬성, LPM의 유한 언어 지표 |
| Replay·alignment | 기존 native replay/Dijkstra, 정규화 fitness, 별도 탐색·비용 profile | Token repair·silent tie, A*의 하한 근거, 근사와 한도 종료, 일반 tree 직접 알고리즘과 net 변환 조합 |
| Precision·generalization | Token/optimal-prefix ET, alignment 투영 automaton, DFG precision, transition visit 지표 | 모집단·빈 prefix·termination·duplicate label·silent closure·zero denominator |
| Anti/multi-alignment | 명시한 유한 길이의 실제 모델 언어와 weighted edit 목적함수 | Anti max-min과 multi sum/minimax의 차이, 참조 discount/정규화, horizon 밖 optimum |
| Declare·skeleton·temporal profile | 규칙 발견, 모든 activation 평가, 시간 분포와 위반 witness | Vacuity·support/confidence 분모·진행 중 pending, negative succession 정의, sample/population variance |
| 통계·성능·필터 | 활동·variant·자원·기간·구간·KDE·cube·spectrum, typed selection과 원본 추적 | 실제 시작과 인접 완료 gap, 결측·동률·overlap·case/event 분모, 선택 후 생긴 adjacency |
| 모델 성질·변환 | 표현별 발화, reachability/soundness/complexity, 방향별 변환·축약·분해·equation | 검사된 모델 클래스, 증명/반례/한도 상태, 변환 전후 보존할 언어·token/guard 의미 |
| Feature·decision·clustering·drift | Prefix/target, 수치·문자열 encoder, 명시 학습 모델, 분기·군집·분포 비교 | 학습 시점 누출, label horizon, target과 입력 분리, 관측 순서와 시간창, solver/모델 실행 근거 |
| 조직·simulation·streaming·privacy | 인계/역할/자원 지표, 유한/표본 실행, 누적 상태, 명시 privacy mechanism | 로컬 선택 확률과 전체 경로 확률, queue와 단순 playout, open prefix, neighboring-log 정의·privacy budget |

새 계산은 기존 구현을 이름만 바꿔 늘린 목록이 아니다. 예를 들어 `discover_inductive_dfg`는
trace를 임의로 생성하지 않고 DFG를 직접 재귀하며, POWL은 부분순서 모델을 실제 표현한다.
반대로 유한 region 발견을 PM4Py의 모든 ILP variant가 끝난 것으로 기록하지 않는다.

## 4. Object-Centric 계산 구조

| 계산군 | 실제 코드가 다루는 내용 | 구분해서 검토할 정의 |
|---|---|---|
| 실행 추출·variant | 공유 E2O 연결, leading object scope, event-object incidence 동치 | 공유 Agent object로 독립 Task가 합쳐지는 문제, 실행 overlap, graph 동치에 포함할 label·qualifier·순서 |
| EOG·OCDFG·관계 graph | 객체별 선후행, 객체형별 활동 흐름, interaction/descendant/inheritance 및 ET-OT·OTG | Event-pair·unique object·total object 빈도의 분모, O2O 사실과 관측에서 유도한 관계 |
| OCPN·SAW 발견 | 객체형별 모델 통합·공동 참여·variable arc 및 arc-weight 관측 분포 | 관측 cardinality와 업무에서 허용되는 cardinality, 발견 모델의 fitness·soundness 근거 |
| OCPN 실행·분석 | 실제 객체 token/binding, projection/hiding/subnet/reduction·도달 분석 | 일부 객체형을 숨기는 것이 실행 의미를 보존하는 조건, OCPA Subprocess 참여 검사와 soundness 차이 |
| Object-Centric Causal Net | Marker group·입출력 binding에 따른 별도 모델·실행 | OCPN과 동일 자료구조가 아니며 방향별 변환은 지원되는 부분집합과 손실을 명시 |
| Replay·joint alignment·context | Object token replay, flattened replay, event-once joint 정렬, prefix/context 평가 | Flattened 평균과 공동 위반의 차이, token flooding·silent 탐색, PIX concrete binding과 OCPA context 정의 |
| 성능 | EOG input arrival와 OPERA token arrival를 구분한 시간 계산 | Waiting/service/sojourn/synchronization/pooling/lagging/readiness의 입력 집합과 관측 시작 시각 |
| 규칙·qualifier | 활동·객체 참여·순서·cardinality·성능 조건과 E2O/O2O 검증 | 모든 activation, source×target 관계쌍, 시점별 속성 as-of 경계, unknown과 violation 구분 |
| Feature·선택·변환 | Event/object/execution별 feature, 시간창·sequence/table, 명시 closure를 갖는 선택 | 공유 객체를 통한 누출, 미래 remaining target, event 삭제 후 관계 유지, OLAP·merge·interleaving의 독립 기능 |
| Simulation·action 분석 | OCPN과 causal-net의 별도 binding playout, 시간 패턴·일정·구조/marking/성능 영향 | Model final-state와 horizon·정책, 일정 heuristic/최적성, 과거 성능 변화와 인과적 개선의 차이 |

Schumpeter가 실제 Agent 행동을 실행하고 Hub 정책을 배포하는 부분은 위 계산 결과를 사용하는 계층이다.
PIX의 action candidate·schedule·impact 계산이 외부 행동을 직접 실행하지 않는다.

## 5. 눈으로 확인할 계산 차이와 반례

다음 사례는 모든 알고리즘의 승인 대신 사용할 수 없다. 서로 다른 정의가 결과를 바꾸는 지점을
검토할 작은 기준 사례이며, 실제 행의 테스트와 함께 판단한다.

| 사례 | 명시한 PIX 정의에서 확인할 결과 | 이 기준이 깨지면 철회할 판단 |
|---|---|---|
| 모델 A, case `A,A,A,A,empty` | Token pooled fitness 8/9, case mean 4/5. 두 수치를 하나로 부르지 않음 | 모집단 또는 token witness에서 이 분모가 성립하지 않으면 해당 fitness profile 재검토 |
| 다른 transition인 A 뒤에 B/C 선택, 관측 AB | Deterministic token-prefix와 모든 optimal stop의 alignment-prefix precision은 다를 수 있음 | 동일 prefix의 가능한 marking을 누락/중복하거나 tie 정책과 witness가 다르면 철회 |
| `A,B,A`에 response A→B | 마지막 A의 미완료 의무가 존재. 닫힌 case는 위반, 열린 case는 pending 가능 | 첫 A만 보고 전체를 만족 처리하면 해당 규칙 구현 철회 |
| 입력 도착 09:00/09:10, 시작 09:15, 완료 09:25 | ready-input wait 5분, first-input wait 15분, service 10분은 다른 정의 | 시작 시각 없이 service를 0이나 gap으로 생성하면 해당 시간 계산 철회 |
| 실제 구간 09:00–09:10, 09:10–09:20 | Strict overlap은 없음, closed/inclusive endpoint는 접촉을 포함 | 선택한 경계 정책과 관계 witness가 불일치하면 재검토 |
| Trace `{ABC,A}`의 발견 | Plain sequence의 독립 optional B/C와 묶인 optional BC는 허용 언어가 다름 | 같은 모델이라고 기록하거나 관측 trace만 재생해 차이가 없다고 판단하면 철회 |
| 같은 Agent, 서로 다른 Task의 이벤트 | Agent까지 연결에 넣은 connected component는 두 Task를 합칠 수 있음 | Task별 실행이 요구되는데 선택한 scope가 합쳐도 그대로 승인하지 않음 |
| 유한 horizon 3의 anti/multi 결과 | 길이 3 이하의 optimum은 완료될 수 있으나 길이 4 이상은 판단하지 않음 | 한도 종료·누락된 합법 언어가 있는데 전역 optimum이라고 표시하면 철회 |
| 다음 활동/remaining time feature | 정답 target은 별도 열. 예측 cutoff 뒤 사실을 입력 feature로 넣지 않음 | 공유 case/object 또는 미래 사실이 학습·평가 경계를 넘으면 결과 해석 철회 |

각 계산의 domain 검토는 [기존 검토 절차](2026-09-13_PIX_DOMAIN_REVIEW_WORKFLOW.md)를 따른다.
현재 구현 profile의 존재와 선생님의 개별 의미 승인은 별도 상태다. 이미 합의된 정의는 반복 승인
대상으로 만들지 않고, 실제로 달라지는 단위·분모·순서·목적함수만 검토 항목으로 드러낸다.

## 6. 참조 조사에서 바로잡은 내용

1. **Count2Vec**: 고정 PM4Py 소스는 `binary=False`, `ngram_range=(1,1)`의 unigram count baseline이다.
   학습된 dense embedding 알고리즘으로 분류하지 않는다. PIX에서는 `FeatureSpec(encoding="count",
   ngram_min=1, ngram_max=1)`의 활동 토큰 집계와 연결하며, 추가 text attribute context는 별도 범위다.
2. **PM4Py stochastic Petri-net playout**: 해당 소스는 stochastic map의 weight로 발화 대상을 고른다.
   출력 로그의 인공 1초 timestamp 증가를 실제 서비스 시간 분포 sampling으로 해석하지 않는다.
   Timed stochastic 모델·분포 fitting·queue simulation은 따로 확인해야 한다.
3. **PM4Py DFG CLASSIC playout**: 우선순위 큐를 이용해 확률 순서의 경로를 열거하는 경로다.
   PERFORMANCE의 경로·시간 sampling과 구분한다. PIX의 `enumerate_dfg`와 `playout_dfg`도 별도다.
4. **OCPN/OCCN**: 객체 중심 모델이라는 공통점만으로 합치지 않는다. 두 실행 의미·simulation과
   양방향 변환 행을 각각 보존한다.

새 SaCoFa는 별도 계산 진입점으로 behavioral prefix 선택과 count release를 수행한다. PRIPEL의
현재 재구성 결과는 원본과의 matching witness를 포함하는 **private 진단 자료**다. 이 결과 전체를
안전한 익명화 배포물로 표시하지 않으며, 공개할 출력과 조건부 privacy 보장의 검증은 따로 기록한다.
마찬가지로 transformer adapter의 계약 테스트가 실제 학습 모델 실행을 대신하지 않는다.

이 내용은 SCOPE-01에 고정한 배포 소스의 정적 대조다. 전체 참조 라이브러리를 실행해 결과를
대조했다는 주장이 아니며, 당시 표현이 과도했던 부분을 새로운 코드의 지원 요구로 확대하지 않는다.

## 7. 검증 기록과 갱신 조건

행별 registry는 실제 모듈·공개 함수·선언된 profile·테스트 파일·참조 variant·잔여 차이를 연결한다.
`file_snapshot`의 hash는 분류한 코드 시점을 고정한다. `.artifacts`의 작업 보고서는 로컬 보조 근거이며,
공개 저장소에서는 소스·테스트·이 문서의 정의를 우선 확인할 수 있어야 한다.

구조 검증은 다음 명령으로 수행한다.

```text
python tools/check_mining_registry.py
python tools/check_mining_registry.py --strict-hashes
```

이 검사는 행 누락·중복·존재하지 않는 함수/파일·snapshot 변경을 찾는다. 알고리즘을 실행하지 않으며
수학적 동등성을 판정하지 않는다. `--strict-hashes`는 문서 작성 후 코드 변경을 감지하는 용도이고,
코드를 정상적으로 개선한 뒤에는 해당 행의 정의와 테스트를 다시 확인하고 snapshot을 갱신한다.

**통합 QA 결과:** 최종 전체 pytest는 **8,362 passed / 27 skipped / 1,169 subtests passed**,
실패 0건이다. 27개 skip은 로컬 corpus opt-in 11개, PyArrow runtime 14개,
OS symlink 1개, browser collection 1개로 나뉜다. 여러 작업 보고서의 중첩된 수를 더하지 않았다.

PM4Py·OCPA와 선택 수치/학습 라이브러리가 없는 격리 wheel에서 runtime 파일 191개가
소스와 일치했고, 82개 모듈 import와 CC/OC 계산·결과 JSON 흐름을 검사했다.
실제 ADL XES 8개와 OrderManagement OCEL은 별도의 원본 직접 집계와 일치했다.
ProcureToPay OCEL은 객체 속성 이력의 같은 name/time 중복 때문에 계산 전에 거부되어
계산 성공으로 집계하지 않았다. 저장·복원 및 실제 입력의 세부 근거와 선택적인 SciPy·Transformer
실행 제한은 [검증 기록](../version/2026-09-15_NATIVE_MINING_VALIDATION.md)에 남겼다.

판단의 유효 범위는 기록된 소스와 선언한 입력·profile이다. 다음 중 하나가 확인되면 관련 행의
상태와 설명을 갱신한다: 독립 oracle 반례, 모델의 합법 실행 witness 누락, 잘못된 분모·시점·동률 처리,
solver의 정수/하한 검증 실패, 결과 저장 후 의미 변화, 선택 의존성 실행 실패, 참조 판본 또는 사용자
요구 정의 변경. 생산 규모의 일반적인 실행 시간·메모리 한계와 최초 수행 성공률은 **알 수 없음**이다.

현재 산출물은 두 도메인을 분리한 native 계산 구조와 그 실제 구현 범위를 확인하는 기록이며,
268개 행의 모든 참조 variant가 대체 완료되었다는 선언은 아니다.
