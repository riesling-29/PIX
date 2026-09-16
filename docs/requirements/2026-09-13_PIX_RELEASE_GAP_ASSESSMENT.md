# PIX 요구사항 기준 구현 격차 평가

기준일: 2026-09-13. 대상: PIX 0.5.0 현재 작업 트리.
이 문서는 [사용자 요구사항](2026-09-13_PIX_SCHUMPETER_USER_REQUIREMENTS.md)의
UR-PIX-01~06을 현재 구현·기존 실행 증거·upstream 소스와 대조한 평가다.
이번 평가는 제품 코드를 수정하거나 테스트를 새로 실행하지 않았다.

영역별 작업·의존 관계·검산 예제·테스트·완료 조건은
[상세 개발 계획](2026-09-13_PIX_DETAILED_DEVELOPMENT_PLAN.md)으로 구체화했다.

**2026-09-14 후속 자료:** [SCOPE-01 대체표](2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md)는
PM4Py 2.7.23.8·OCPA 1.3.4 공식 wheel을 직접 대조한 334개 검토 항목과 정적 연결 검증을 제공한다.
아래의 15개 기능군 평가는 당시 기준으로 유지하며, 함수·variant별 최신 범위와 경계는 새 표를 따른다.

**2026-09-16 시각화 결정 갱신:** 아래 시각화 평가는 9월 13일의 자산 기록이다. 이후 native 시각화를 확장했으나 DFG·OCDFG 실제 샘플에서 간선·라벨 혼잡을 확인했고, 사용자는 **Graphviz를 신규·기존 graph 모두의 기본 배치로 채택**했다. 자체 배치는 신규 문서의 명시적 실험 옵션, ELK는 기존 문서의 명시적 옵션으로 남기며 자동 fallback은 하지 않는다. OCPA의 *Variant Calculation and Layouting*에 대응하는 객체 instance별 shared-event chevron도 추가한다. 현재 결정·검증 조건은 [Graphviz·OC variant 변경 요구사항](2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md)을 따른다. 이 갱신은 아래 역사 평가·실행 수치를 새 검증 결과로 바꾸지 않는다.

## 1. 평가 기준과 범위

사용자의 목표는 PM4Py·OCPA 계산 기능을 PIX 자체 구현으로 대체하는 것이다.
Import, 모델 발견, alignment 몇 가지가 있다는 사실만으로 전체 대체 완료를 판단하지 않는다.
반대로 Schumpeter Hub와 Agent 실행기를 완성해야 PIX를 출시할 수 있다고 요구하지도 않는다.

현재 PIX에는 독립적인 데이터·계산 계약, 실제 발견·conformance 알고리즘, 결과 저장과
시각화·설치 검증이 있다. 아래 표는 이를 인정하면서 추가 구현과 의미 대조, 검증 부족을 나눈다.

| 표기 | 의미 |
| --- | --- |
| 구현 있음 | 공개 사용 경로와 실제 계산 구현을 확인. 모든 upstream variant와의 동등성·일반 성능까지 인정하는 표시는 아님 |
| 부분 구현 | 해당 도메인 질문의 일부만 계산하거나 입력·모델·의미 범위가 제한됨 |
| 정의 다름 | 같은 계열의 기능이 있지만 집계 대상·동치·수식이 달라 동일 결과를 주장할 수 없음 |
| 대응 구현 없음 | 공개 API·제품 소스·관련 계약에서 대응 계산을 찾지 못함 |
| 검증 부족 | 구현 존재와 별개로 필요한 데이터·규모·환경의 실행 근거가 부족함 |

첫 출시의 정확한 알고리즘·변형 목록과 합격 조건은 아직 미정이다.
아래 작업 순서는 전체 대체 목표를 줄이는 승인이 아니라 구현 의존성에 따른 제안이다.
기존 라이브러리의 함수 이름·내부 자료구조·Graphviz 사용을 그대로 복제할 필요는 없다.
같은 업무 질문과 계산 정의를 지원하는지, 다른 정의를 채택하는지, 미지원인지가 드러나야 한다.
동일 문제를 푸는 탐색 backend들은 결과·설정·실용 성능을 비교해 통합 가능 여부를 판단한다.

## 2. 비교 판본

| 대상 | 실제 소스 대조 기준 | 기준일에 확인한 공식 배포 정보 | 남은 판본 대조 |
| --- | --- | --- | --- |
| PM4Py | 로컬 2.7.23.3, `3329bbcbadce8764f7df660fd88636c30793fbd0` | PyPI 2.7.23.8, 2026-09-01 배포. release SHA `24a3bf610aea6ecc4938b1864b3ad71fcfb82084` | 2.7.23.3 이후 계산 변경 전체를 아직 대조하지 않음 |
| OCPA | 로컬 소스 1.3.3, `de056e0203a3fa4a9bbc19a95e001eada323074a` | PyPI 1.3.4, 2025-09-19 배포. 확인한 main SHA는 로컬과 같음 | 1.3.4 배포본과 소스 1.3.3 사이의 전체 알고리즘 동일성은 미검증 |

공식 메타데이터 근거: [PM4Py PyPI](https://pypi.org/project/pm4py/2.7.23.8/),
[OCPA PyPI JSON](https://pypi.org/pypi/ocpa/json),
[PM4Py release commit](https://github.com/process-intelligence-solutions/pm4py/commit/24a3bf610aea6ecc4938b1864b3ad71fcfb82084),
[OCPA main commit](https://github.com/ocpm/ocpa/commit/de056e0203a3fa4a9bbc19a95e001eada323074a).
확인 시각과 원문 URL은 `.artifacts/pix-release-gap-2026-09-13/upstream.json`에 기록했다.
최신 버전 번호를 확인한 것과 최신 배포본의 전체 계산을 감사한 것은 구분한다.

## 3. 도메인 기능별 현재 상태와 남은 일

각 행은 공수가 같은 단위가 아니다. PM4Py·OCPA의 중복 기능을 묶었으므로 행 수를 완성도 분모로 쓰지 않는다.

| 영역과 사용자가 묻는 질문 | 현재 PIX | 남은 작업 |
| --- | --- | --- |
| **입력·보존:** 실제 로그를 계산 가능한 형태로 읽는가? | **구현 있음.** OCEL 1/2, 문서화한 OCEL 2.1 pre4 profile, XES/MXML, 매핑한 업무 표. Native CaseLog와 canonical OCEL, 원본 순서·metadata·관계·이력 보존 | 추가 생산자·구조의 실제 로그 검증. XES/MXML writer, OCEL 2.1 writer 등은 현재 import 범위 밖이며 출력 대체 목록에서 별도 판단 |
| **Case 분석 연결:** XES를 읽은 직후 일관된 분석이 가능한가? | **부분 구현.** CaseLog→원본 순서 TraceSet→발견/replay/alignment/precision. DFG·temporal 공개 경로는 OCEL 중심 | CaseLog/TraceSet의 순서를 유지하는 DFG·variant 빈도·통계·시간 분석 연결. 시각 없는 로그와 시각 동률·역전의 해석 명시 |
| **발견:** 어떤 프로세스 모델이 설명력이 있는가? | **부분 구현.** 자체 `pix.im.v1`, `pix.inductive_cut.v1`, tree→Petri net, DFG/OCDFG, 관측 로그의 수용 witness를 확인하는 OCPN 발견 | IMf·IMd, Alpha/Alpha+, Heuristics, ILP, POWL 등 발견군. PM4Py의 genetic·Split·transition system·prefix tree·batches/correlation 등도 전체 inventory에 포함해 실제 지원 방식과 필요 의미를 대조 |
| **전통적 conformance:** 어디가 어긋나며 얼마나 맞는가? | **부분 구현·정의 다름.** Token replay, bounded Dijkstra alignment, 자체 enabled-prefix precision | 정규화 replay/alignment fitness, ET 계열 precision의 대응, generalization·simplicity. 비용 설정과 다른 모델 alignment, A*/분해 탐색 등 성능·범위 확장 대조 |
| **Execution·variant:** 객체들이 엮인 실행과 반복 구조는 무엇인가? | **구현 있음·정의 다름.** Connected components/leading-object 실행 추출, qualified E2O incidence의 exact variant | OCPA EOG variant와 동치 정의 대조. 현재 추출은 O2O를 사용하지 않고 variant는 O2O·attribute를 제외. 관계·속성을 포함하는 추가 관점은 별도 계산 |
| **객체 중심 conformance:** 객체 간 결합까지 모델과 맞는가? | **부분 구현·정의 다름.** Concrete object를 함께 탐색하는 실제 joint OCPN alignment, binding-prefix context fitness/precision | Object-centric token replay 및 계수 기반 fitness. OCPA context 지표와 다른 PIX 정의를 명시하고, 원래 정의 지원 또는 대체 타당성 검증 |
| **시간·병목:** 어디서 기다리고 무엇 때문에 지연되는가? | **부분 구현.** 관측 event gap, 명시적 start attribute가 있는 service time | Case duration·arrival·overlap·cycle time, business calendar. 객체 중심 flow/sojourn/synchronization/pooling/lagging/readiness, token 방문 기반 waiting 및 모델 annotation |
| **통계·필터:** 어떤 모집단과 하위 로그를 분석하는가? | **부분 구현.** 객체형·qualifier 선택, 일부 활동·시작/종료 집계 | 활동/variant/시간/속성/경로/재작업/빈도 필터, 분포·비중·coverage, execution selection. 필터 뒤 관계·이력·분모·출처가 유지되는 sublog 계약 |
| **규칙·모니터링:** 어떤 행동·객체·시간 제약을 어겼는가? | **부분 구현.** Count, Response, Precedence, NotCoexistence, TimedResponse의 5종과 pending/vacuous/violation 구분 | Declare 발견·평가, log skeleton·temporal profile·footprints. OCPA control-flow·object cardinality·performance constraint graph와 threshold/조합 평가 |
| **OCEL 2 관계·이력 계산:** 그 시점의 객체 상태와 관계가 행동에 맞았는가? | **부분 구현.** Qualified E2O/O2O와 timed attribute assignment 보존·조회, 일부 E2O qualifier 선택 | O2O qualifier conformance, 시점별 객체 속성과 E2O qualifier 조건의 결합 계산. 보존된 사실을 실제 평가식에 연결 |
| **모델 표현·교환·분석:** 모델을 교환·축약하고 성질을 검사하는가? | **부분 구현.** Process tree, weighted P/T net, concrete-object OCPN, tree→net, 자체 모델 JSON, 발화 의미 | BPMN/POWL/Heuristics net 등 표현·변환, PNML/BPMN 입출력. WF-net/soundness/boundedness/liveness·invariant·reachability·reduction. 범용 OCPN projection/hide/reduction/enhancement |
| **Feature·고급 분석:** 예측·분류·변화 탐지에 필요한 정보를 만드는가? | **대응 구현 없음.** Trace/execution 등 재료만 있음 | Case/event/execution feature, prefix/target·tabular/sequential/time-series encoding, decision mining·clustering·concept drift·log/model 비교. 미래 정보 누출 없이 학습용 데이터 생성 |
| **조직·자원, simulation, streaming:** 누가 협업하며 다른 조건에서는 어떻게 흐르는가? | **대응 구현 없음.** 모델 발화 primitive와 open 규칙 평가는 있음 | 자원 인계·협업·역할 분석, playout·확률/시간 simulation, stream 관리·증분 DFG/replay/규칙. Open 규칙 평가는 streaming 계산 엔진과 별개 |
| **Action·impact 계산:** 어떤 개입 후보가 가능하고 무엇에 영향을 주는가? | **대응 구현 없음.** Recommendations/recovery 등은 placeholder | OCPA AOPM temporal pattern matching, action 후보·conflict/precedence plan, 구조·운영·성능 impact 계산. 계산은 PIX inventory에 포함하고 실제 Agent 실행·배포는 Schumpeter에 둠 |
| **그래프와 결과 전달:** 계산 구조와 증거를 사람이 확인하는가? | **9월 13일 기준 구현 있음.** 버전 있는 결과/모델 JSON, SVG·오프라인 ELK viewer와 브라우저 검증 | 당시 남은 일은 새 모델·지표·진단 표시와 큰 그래프 검증. 기본 배치에 대한 현재 결정은 위 9월 16일 갱신이 우선하며, Graphviz 기본값과 OC variant chevron을 별도 검증 |

### 의미 혼동을 피해야 하는 사례

1. **XES import 완료와 case 분석 전체 완료:** 현재 `case_traces`는 source order를 유지하지만,
   DFG·시간 분석을 위해 OCEL로 우회하면 시각을 요구하고 객체 trace의 시각 정렬 정책을 거친다.
   따라서 우회를 원본 순서의 완전한 대체라고 볼 수 없다.
2. **이미 있는 IM과 noise-aware discovery:** 현재 discovery 계약은 0이 아닌 noise threshold를
   거절한다. 실데이터에서 드문 행동을 처리하는 IMf 등의 구현과 검증은 남아 있다.
3. **같은 이름의 precision/fitness:** PIX object context는 참여 객체 binding-prefix 집합을
   micro 집계하며 OCPA 지표와 다르다고 소스에 명시한다. 자체 정의의 검증과 OCPA 정의의 대체는 별도다.
4. **event gap과 waiting/synchronization:** 두 이벤트 사이의 시간 차이만으로 어느 객체를
   기다렸는지나 실제 처리·동기화 시간을 정할 수 없다. 이벤트·모델·객체 관점의 정의가 필요하다.
5. **관측 수용과 모델 soundness:** 현재 OCPN의 관측 fitting witness는 의미 있는 구현 자산이다.
   그것이 보지 못한 모든 실행의 soundness를 증명하지는 않는다. 다만 무한 객체 생성이나 모든 종류의
   OCPN soundness를 기존 라이브러리 대체 요구만으로 새로운 필수 조건으로 추가하지 않는다.

## 4. 이미 확보된 검증 근거와 남은 검증

| 기존 실행 증거 | 인정할 수 있는 범위 |
| --- | --- |
| 2026-09-12 Python 3.11.15: **4,184 passed + 284 subtests, 14 skipped** | 기록된 구현 계약과 fixture의 회귀 검증. 전체 upstream 계산 목록의 구현률은 아님 |
| Chromium **13 passed**, JavaScript **98 passed** | 해당 viewer·layout 경로의 검증 |
| 독립 설치 wheel: import core/extras **각 20 checks**, native pipeline | 독립 패키지 설치와 계산 경로. 필수 PM4Py/OCPA runtime 의존성 없음 |
| 현재 파일과 wheel 검증 artifact의 runtime **106개 hash 일치** | 기존 설치 검증이 가리키는 코드가 현재 코드와 대응함을 이번 읽기 전용 검토에서 확인 |
| 실제 XES: **11개 corpus 테스트 + 기존 92개 회귀 통과** | 9개 고유 로그/10개 물리 입력 전체 import 및 독립 원본 대조. 분석은 정해진 표본 범위 |
| 실제 OCEL JSON/bundle: **1,210 events / 1,701 objects / 5,767 E2O** | 해당 두 표현의 canonical 동일성. 모든 객체 중심 알고리즘의 실데이터 검증은 아님 |
| 독립 계산 oracle: classical/joint alignment, finite context, constraint truth | 작은 유한 사례를 별도 계산법과 대조한 정확성 근거. 독립 정답 검증이 없는 상태는 아님 |

기존 JUnit·JSON 및 hash를 대조했으며 이번 평가에서 새 실행 결과를 만들지는 않았다.
자세한 기록은 [0.5.0 구현 검증](../version/v0.5.0_IMPORT_IMPLEMENTATION.md),
[실제 XES 검증](../version/v0.5.0_XES_CORPUS_2026-09-13.md),
[0.4.0 모델 평가 검증](../version/v0.4.0_MODEL_EVALUATION_IMPLEMENTATION.md)을 참조한다.

남은 안정성 작업은 다음과 같다.

- **계산별 합격 근거 연결:** 입력, 알고리즘/변형, 수식, 기대 결과, 실패·제한 상태,
  테스트·실행 artifact를 한 목록에서 연결한다. Upstream 결과는 비교값이며 버그까지 정답으로 고정하지 않는다.
- **실제 규모 검증:** 병원 로그 451,359개 이벤트는 전체 import를 검증했으나 discovery/replay는
  32 cases/118 events 표본이었다. 실제 OCEL의 여러 객체 결합·관계·이력과 긴 실행에 대한 계산도 확대한다.
- **탐색 사용성:** HH102 weekends 7 cases/420 events는 silent 탐색 상한 256에서 모두 제한됐고,
  상한 1,024에서 7개 모두 완료됐다. 최대 관측 탐색 상태는 677이었다. 한도를 정확히 보고하는 것에 더해
  사용 목표 규모에서 완료율·실행 시간·최대 메모리를 측정하고 병목을 개선한다.
- **표시한 환경 지원:** `Python >=3.10` 선언에 대해 현재 증분 코드의 3.10 실행은 미검증이다.
  지원할 OS/Python 범위를 정하고 해당 조합의 설치·핵심 회귀를 확인한다. 현재 `.github` CI workflow는 없다.
  CI 추가는 안정성을 유지하기 위한 제안이며 모든 OS 지원을 새 요구로 정한 것은 아니다.
- **공개 snapshot 정리:** v0.5.0의 소스·테스트·문서 일부가 미커밋이다. 출시 snapshot/tag와 공개 라이선스는
  남은 배포 작업·제품 결정이다. Wheel 제작과 독립 설치 검증은 이미 수행했으므로 처음부터 만들 필요는 없다.

## 5. 남은 구현을 진행하는 순서 제안

다음은 의존 관계와 일상적인 분석 흐름을 기준으로 나눈 작업 묶음이다.
동일 공수의 단계나 첫 출시에서 나머지를 제외한다는 뜻은 아니다. 테스트는 마지막 묶음까지 미루지 않는다.

| 순서 | 만들 결과 | 단계별 합격 확인 |
| --- | --- | --- |
| **A. 대체 목록 고정** | 최신 판본 차이를 포함한 알고리즘·변형별 목록. 같은 정의/의도한 다른 정의/미지원 구분 | 기존 구현에 연결한 계산 계약과 검증 근거. 공개 기능·별도 backend·중복 wrapper를 혼동하지 않는 누락 검토 |
| **B. 일상 분석 경로 완성** | CaseLog의 DFG·통계·필터·variant/time 연결, OCEL 관계·이력 조회와 sublog | 손으로 계산한 작은 XES/OCEL의 순서·분모·관계·시점별 값, 실제 로그의 해당 분석 결과 |
| **C. 품질·병목 계산 확장** | 정규화 fitness, precision 정의 대응, generalization/simplicity, object replay, 객체 중심 performance | 독립 정답, upstream 차이 설명, 결측·동률·루프·동시성·실패 사례, 원본 모집단에 대응하는 지표 |
| **D. 발견·모델 생태계 확장** | IMf/IMd·추가 miner, 모델 표현·변환/교환·분석·축약, alignment 범위/성능 | 잡음 수준·병렬/루프 구조별 사례, 변환 전후 의미, 알려진 sound/unsound 모델, 탐색 완료·한도 근거 |
| **E. 객체·규칙·개입 계산 확장** | 관계/속성 조건 conformance, 넓은 constraint graph, Declare 계열, AOPM 후보·계획·impact | 객체 버전/시점·충돌·선행 제약별 기대 판정. 계획 가능성과 실제 성공·인과 효과의 주장을 구분 |
| **F. 나머지 계산군 구현** | Feature/encoding·decision/clustering/drift, 조직/자원, simulation, streaming 등 inventory의 남은 기능 | 정보 누출 없는 분할, seed/확률 조건, late event·checkpoint, 자원 지표의 분모 등 기능별 검증 |
| **G. 출시 범위 전체 검증** | A에서 정한 모든 항목의 구현·문서·설치·실데이터·환경 증거 완결 | 단계마다 누적한 회귀 + 최종 지원 범위 실행. 처리 시간·메모리·정확/제한/실패 상태를 공개 가능한 기록으로 정리 |

Schumpeter Hub, Agent 연결부의 실제 도구 실행, Skill 배포, 물리 장치 제어는 이 PIX 잔여 구현량에
포함하지 않는다. 다만 이 소비자들이 활용할 수학적 feature·constraint·action/impact 계산은
기존 계산 라이브러리 대체 목록에서 누락하지 않는다. 처음 보는 작업의 무실패·최적 경로 보장은 별도 연구 가설이다.

## 6. 소스 근거와 과거 문서의 시점

PIX의 확인 경로:

- 입력·case 연결: [adapters](../../src/pix/event_log/adapters.py),
  [DFG](../../src/pix/compute/dfg.py), [temporal](../../src/pix/compute/temporal.py).
- 발견·모델: [discovery 계약](../../src/pix/contracts/discovery.py),
  [OCPN discovery](../../src/pix/compute/ocpn_discovery.py),
  [model 계약](../../src/pix/contracts/models.py).
- 평가: [replay 계약](../../src/pix/contracts/replay.py),
  [precision](../../src/pix/compute/precision.py),
  [joint alignment](../../src/pix/compute/object_conformance.py),
  [object context](../../src/pix/compute/object_context.py).
- 객체·규칙: [execution 계약](../../src/pix/contracts/execution.py),
  [variants](../../src/pix/compute/variants.py),
  [constraint 계약](../../src/pix/contracts/constraint.py), [OCEL 모델](../../src/pix/ocel/model.py).
- 공개 기능과 미구현 경계: [api](../../src/pix/api.py),
  [recommendations](../../src/pix/intelligence/recommendations.py),
  [recovery](../../src/pix/compute/recovery.py).

로컬 upstream 근거의 루트는 `D:\ChantaResearchGroup\PIX-References`다.

| 대상 | 비교한 핵심 경로 |
| --- | --- |
| PM4Py | `pm4py-upstream/pm4py/{discovery,conformance,stats,filtering,convert,analysis,org,sim,ml}.py`, `algo/{discovery,conformance,evaluation,analysis,decision_mining,clustering,concept_drift}`, `streaming/algo` |
| OCPA | `ocpa-upstream/ocpa/algo/discovery`, `conformance/{precision_and_fitness,token_based_replay,constraint_monitoring}`, `enhancement/{event_graph_based_performance,token_replay_based_performance,ocpn_analysis}`, `predictive_monitoring`, `ocel2_use_cases`, `util/{process_executions,variants,filtering,aopm}` |

과거 계획은 [native 구조 검토](../architecture/3_PIX_NATIVE_PROCESS_MINING_STRUCTURE_REVIEW.md),
[2026-09-12 비교 갱신](../reference-analysis/comparison/2_PM4PY_OCPA_STRUCTURE_REFRESH_2026-09-12.md)에 있다.
그 문서 작성 뒤 구현된 기능이 있으므로 과거의 “미구현” 문장을 현재 상태로 옮기지 않았다.

## 7. 판단의 유효 범위·철회 조건

- **근거 강도:** 공개 API와 계산 소스·계약의 존재/부재, 보관된 실행 결과는 직접 확인했다.
  기능군 단위의 격차 판단 근거는 있지만 최신 배포본 전체의 완전한 목록을 확정한 것은 아니다.
- **알 수 없음:** 전체 대체율, 남은 인시·달력 일정, 실사용 전반의 최대 규모·최대 메모리·호환율.
  알고리즘 수·파일 수·테스트 수 또는 버전 번호로 이를 추정하지 않는다.
- **유효기간:** 2026-09-13에 읽은 작업 트리·명시한 upstream 판본·검증 artifact에 한정한다.
  새 코드, 범위 결정, upstream 변경, 새로운 테스트 근거가 생기면 관련 행을 갱신한다.
- **철회·수정 조건:** 대응 공개 구현이나 독립 검증 증거가 추가로 확인되면 “없음/검증 부족”을 수정한다.
  지원 profile에서 의미 보존 실패·오답이 재현되면 그 profile의 기존 긍정 판단을 철회하고 회귀 검증을 추가한다.
  측정 결과로 우선순위의 전제인 의존 관계·사용성 개선 효과가 깨지면 작업 순서를 바꾼다.

## 8. 최종 판단

사용자 요구사항 기준으로 PIX는 **입력 기반과 실제 계산 코어를 확보했고, 그 위에 PM4Py·OCPA의
나머지 계산군을 크게 확장해야 하는 단계**다. 남은 일은 발견·평가·시간/통계·모델 분석의 확장과,
feature·조직/자원·simulation·streaming·action/impact 등 새 기능군 구현, 출시 범위 전체 검증이다.
정확한 잔여 공수는 현재 알 수 없으며, A의 목록과 초기 구현 묶음의 실측이 있어야 일정 추정 근거가 생긴다.
