# PIX Case-Centric 계산 행별 구현 범위

이 문서는 Case-Centric 검토 항목을 업무 질문별로 읽기 위한 자료다. 기준일은 2026-09-15이며,
고정한 PM4Py 2.7.23.8·OCPA 1.3.4의 대체 범위를
[실제 구현 registry](implementation_registry.json)에서 옮겼다.
전체 구조와 통합 검증 결과는 [합집합 구현 구조](../2026-09-15_PIX_NATIVE_MINING_UNION.md)에 기록한다.
Object-Centric 항목은 [별도 문서](OBJECT_CENTRIC_COVERAGE.md)에서 확인할 수 있다.

한 행은 하나의 검토 단위다. 하나의 알고리즘과 일대일로 대응하지 않으며, 행 수나 상태별 개수는 완성률이 아니다.
실제 함수를 연결했다는 사실, 특정 PIX 정의를 계산한다는 사실, 참조의 모든 선택지와 결과가 같다는 판단은 구분한다.
아래의 `native_profile`도 참조 전체 대체 검증 완료를 뜻하지 않는다.

| 상태 | 이 문서에서의 의미 |
|---|---|
| `native_profile` | 아래 명시된 PIX 계산 정의를 실제 함수에서 수행한다. 참조의 모든 variant와의 동등성은 별도 검증 대상이다. |
| `partial` | 해당 기능의 일부 또는 더 좁거나 다른 정의를 계산한다. 남은 차이를 포함한 행 전체 대체 완료로 보지 않는다. |
| `external_runtime_unverified` | 어댑터·계약과 실행 경로는 있지만 실제 외부 학습·수치 runtime의 실행 근거가 충분하지 않다. |
| `unimplemented` | 대응 계산 경로가 없다. 비슷한 입력·출력이나 공통 보조 함수의 존재만으로 구현으로 세지 않는다. |

Case-Centric 입력은 case에 속한 활동열이다. 원본 기록 순서·시간 정렬·lifecycle 구간·진행 중 prefix는
서로 다른 해석이므로 각 계산의 정의에 따라 구분한다. 객체형을 펼친 OCEL projection도 이 도메인에서
계산할 수 있지만, 여러 객체가 한 event에 공동 참여하는 joint replay나 alignment와 같은 계산은 아니다.

업무 질문과 검토 대상 입출력은 대체표가 요구한 범위다. 현재 PIX가 그 전체를 지원한다는 뜻은 아니다.
각 행의 **PIX 계산 정의**는 registry에 기록된 지원 범위이며, 같은 구현 패키지를 공유하는 행에는
공통 정의가 반복될 수 있다. 해당 행에 직접 연결된 함수와 **남은 차이·검증 범위**를 함께 읽는다.
테스트 링크는 관련 검증 코드를 찾기 위한 것으로, 그 파일의 모든 테스트가 해당 행만을 검증한다는 뜻은 아니다.
참조 symbol과 variant의 완전한 원문은 registry에 보존되어 있으며, 여기에는 대표 기능 이름만 표시한다.

근거가 유효한 범위는 registry에 고정한 소스와 입력·계산 정의다. 독립 반례, 누락된 합법 실행,
잘못된 분모·시간 경계·동률 처리, 결과 저장 후 의미 변화, 참조 판본 또는 요구 정의 변경이 확인되면
관련 판단을 수정한다. 생산 규모에서의 일반적인 실행 시간·메모리 한계는 **알 수 없음**이다.

## 범위와 탐색

이 문서에는 51개 구현 패키지의 168개 검토 행이 있다. 현재 상태별 행 수는 `native_profile` 61행, `partial` 106행, `external_runtime_unverified` 1행이다. 참조 전체 대체 검증 완료를 뜻하는 행은 0행이다.

| 구현 패키지 | 다루는 범위 | 검토 행 |
|---|---|---|
| [CC-INDUCTIVE](#cc-inductive) | IM, IMf, IMd and IM to BPMN | 4 |
| [CC-ALPHA](#cc-alpha) | Alpha and Alpha+ | 2 |
| [CC-HEURISTICS](#cc-heuristics) | Classic and Heuristics++ | 2 |
| [CC-ILP](#cc-ilp) | Region ILP miner | 1 |
| [CC-GENETIC](#cc-genetic) | Genetic miner | 1 |
| [CC-POWL](#cc-powl) | POWL discovery variants | 1 |
| [CC-SPLIT](#cc-split) | Classic Split and SM2 | 2 |
| [CC-FOOTPRINTS](#cc-footprints) | Log/model footprints and conformance | 2 |
| [CC-CAUSAL](#cc-causal) | Alpha/heuristics causal relation | 1 |
| [CC-STATE-VIEWS](#cc-state-views) | View-based state transition system and prefix trie | 3 |
| [CC-TEMPORAL-PROFILE](#cc-temporal-profile) | Temporal profile discovery and diagnosis | 2 |
| [CC-LOG-SKELETON](#cc-log-skeleton) | Log skeleton discovery and conformance | 2 |
| [CC-DECLARE](#cc-declare) | Declare discovery, evaluation and finite playout | 3 |
| [CC-BATCHES](#cc-batches) | Batch recognition | 1 |
| [CC-CORRELATION](#cc-correlation) | Correlation mining without trusted case linkage | 1 |
| [CC-LOCAL-MODELS](#cc-local-models) | Local process model discovery and evaluation | 1 |
| [CC-DFG](#cc-dfg) | Frequency/performance/triples/case-attribute DFG | 4 |
| [CC-REPLAY](#cc-replay) | Forward/backward replay and token-based quality | 5 |
| [CC-ALIGNMENT](#cc-alignment) | Petri-net exact/discounted/approximate/decomposed alignment and normalized quality | 7 |
| [CC-TREE-ALIGNMENT](#cc-tree-alignment) | Process-tree search/DP/MILP/approximate alignment | 1 |
| [CC-DFG-ALIGNMENT](#cc-dfg-alignment) | DFG alignment and DFG precision | 2 |
| [CC-LANGUAGE-ALIGNMENT](#cc-language-alignment) | Log-to-log edit alignment | 1 |
| [CC-CONFORMANCE-APPROX](#cc-conformance-approx) | Variant subset approximation with bounds | 1 |
| [CC-ANTI-ALIGNMENT](#cc-anti-alignment) | Anti-alignment and associated precision | 1 |
| [CC-MULTI-ALIGNMENT](#cc-multi-alignment) | Multi-alignment representative model behavior | 1 |
| [CC-COMPLEXITY](#cc-complexity) | Arc-degree, Cardoso and cyclomatic simplicity | 1 |
| [CC-QUALITY-REPORT](#cc-quality-report) | Explicit multi-metric report composition | 1 |
| [CC-MODELS](#cc-models) | Classical model representations and executable semantics | 4 |
| [CC-CONVERT](#cc-convert) | Direction-specific model conversion | 8 |
| [CC-REACHABILITY](#cc-reachability) | Reachability, WF-net and soundness properties | 3 |
| [CC-OPTIMIZATION](#cc-optimization) | Marking equation and extended lower-bound problems | 2 |
| [CC-SYNCHRONOUS-PRODUCT](#cc-synchronous-product) | Cost-aware log-model synchronous product | 1 |
| [CC-DECOMPOSITION](#cc-decomposition) | Maximal decomposition and recomposition | 1 |
| [CC-REDUCTION](#cc-reduction) | Meaning-preserving net and trace-specific tree reduction | 2 |
| [CC-MODEL-GRAPH](#cc-model-graph) | Structural graph and activity relabeling | 1 |
| [CC-MODEL-SIMILARITY](#cc-model-similarity) | Behavioral/structural/embedding/label similarity | 2 |
| [CC-STATISTICS](#cc-statistics) | Case/event attributes, variants, activity relations and duration distributions | 21 |
| [CC-FILTERING](#cc-filtering) | Explicit case/event/path selection and sampling | 14 |
| [CC-INTERVALS](#cc-intervals) | Lifecycle pairing and case interval views | 2 |
| [CC-TRANSFORMS](#cc-transforms) | Case graph, synthetic boundaries, classifiers, contextual labels and relational merge | 6 |
| [CC-FEATURE-DATASET](#cc-feature-dataset) | Leakage-aware split, prefixes, enriched outcomes and targets | 5 |
| [CC-FEATURES](#cc-features) | Trace, event, temporal and conformance encoders | 5 |
| [CC-EMBEDDINGS](#cc-embeddings) | Word/Doc2Vec and transformer embeddings; learned models remain explicit | 3 |
| [CC-DECISION](#cc-decision) | Decision table, tree, guard and data-net mining | 1 |
| [CC-CLUSTERING](#cc-clustering) | Profile and hierarchical sublog clustering | 2 |
| [CC-DRIFT](#cc-drift) | Bose relation-distribution concept drift | 1 |
| [CC-LANGUAGE-DISTANCE](#cc-language-distance) | Stochastic-language Earth Mover distance | 1 |
| [CC-ORGANIZATION](#cc-organization) | Handover, joint work, subcontract, roles and resource diagnostics | 11 |
| [CC-SIMULATION](#cc-simulation) | Finite/random/stochastic classical playout and FIFO simulation | 7 |
| [CC-STREAMING](#cc-streaming) | Incremental DFG, replay, rules and approximate alignment with persistent state | 9 |
| [CC-PRIVACY](#cc-privacy) | Laplace, SACOFA and PRIPEL privacy calculations | 2 |

통합 테스트 실행 결과와 참조 수치 동등성·독립 증명·privacy 보장은 별도 근거다. 최신 통합 실행 기록은 위의 합집합 구현 구조 문서에서 확인한다.

## CC-INDUCTIVE

**IM, IMf, IMd and IM to BPMN**

### PM-DISC-001

**업무 질문:** 기록된 활동열을 설명하는 noise-free Inductive Miner 모델은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_process_tree_inductive`, `pm4py.discovery.discover_petri_net_inductive`

**참조 선택지:** `IM`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열·빈 trace·classifer 선택과 noise-free 발견 설정.

**검토 대상 결과:** 관측 활동열을 설명하는 process tree 또는 그로부터 변환한 Petri net·초기/최종 marking.

**PIX 계산 정의:**

- pix.im.weighted.v1 / pix.imf.filtered_dfg.v1: 가중 활동열에서 cut과 명시적 fallthrough를 계산한다.

**남은 차이·검증 범위:**

- PM4Py strict-sequence optional-block merging과 모든 옵션 동등성은 미구현·미검증. {ABC,A}에서 PIX가 AB/AC를 추가 허용할 수 있다.

**실제 함수·모델:** [inductive.discover_inductive](../../../src/pix/case_centric/inductive.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_inductive.py](../../../tests/case_centric/test_inductive.py)

</details>

### PM-DISC-002

**업무 질문:** 낮은 빈도의 행동을 잡음으로 다룰 때 어떤 모델과 제외 근거가 나오는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.inductive.algorithm.apply`

**참조 선택지:** `IMf`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 빈도, noise threshold 및 발견 설정.

**검토 대상 결과:** 잡음 처리 정책을 적용한 process tree와 그 모델의 수용·제외 관측 범위.

**PIX 계산 정의:**

- pix.im.weighted.v1 / pix.imf.filtered_dfg.v1: 가중 활동열에서 cut과 명시적 fallthrough를 계산한다.

**남은 차이·검증 범위:**

- PM4Py strict-sequence optional-block merging과 모든 옵션 동등성은 미구현·미검증. {ABC,A}에서 PIX가 AB/AC를 추가 허용할 수 있다.

**실제 함수·모델:** [inductive.discover_inductive](../../../src/pix/case_centric/inductive.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_inductive.py](../../../tests/case_centric/test_inductive.py)

</details>

### PM-DISC-003

**업무 질문:** 전체 trace 대신 DFG·시작·종료 정보만 주어졌을 때 어떤 모델을 발견하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.inductive.algorithm.apply`

**참조 선택지:** `IMd`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 DFG·빈도·시작/종료 활동과 빈 trace에 관한 정보.

**검토 대상 결과:** DFG 정보에 근거해 발견한 process tree.

**PIX 계산 정의:**

- pix.imd.dfg.v1: 빈도 DFG·시작·끝·empty-case 정보에서 직접 재귀한다.

**남은 차이·검증 범위:**

- 참조 IMd의 경계 빈도·redo boundary 정책과 다름. DFG가 잃은 반복·case 상관관계의 복원 및 원본 전체 fitness는 보장하지 않는다.

**실제 함수·모델:** [inductive.discover_inductive_dfg](../../../src/pix/case_centric/inductive.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_inductive.py](../../../tests/case_centric/test_inductive.py)

</details>

### PM-DISC-013

**업무 질문:** Inductive Miner 결과를 BPMN으로 제공할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_bpmn_inductive`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 Inductive Miner 발견 설정.

**검토 대상 결과:** 발견한 process tree를 변환한 BPMN 모델.

**PIX 계산 정의:**

- Inductive process tree 발견은 계산된다.

**남은 차이·검증 범위:**

- IM→tree→supported XOR/AND BPMN composition exists. Native IM cut/fallthrough differences remain; no arbitrary BPMN messages/time/data semantics or upstream structural identity.

**실제 함수·모델:** [inductive.discover_inductive](../../../src/pix/case_centric/inductive.py), [model_conversion.tree_to_bpmn](../../../src/pix/case_centric/model_conversion.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_inductive.py](../../../tests/case_centric/test_inductive.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)

</details>

## CC-ALPHA

**Alpha and Alpha+**

### PM-DISC-004

**업무 질문:** 기본 인과·독립 관계에서 Alpha Petri net을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_petri_net_alpha`, `pm4py.algo.discovery.alpha.algorithm.is_polars_lazyframe`

**참조 선택지:** `ALPHA_VERSION_CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열 또는 인과 관계를 구성할 DFG·시작/종료 활동.

**검토 대상 결과:** Alpha 방식으로 만든 Petri net과 초기/최종 marking.

**PIX 계산 정의:**

- classic 및 Alpha+의 causal maximal pair와 short-loop 복원. loop_attachment exact/containing을 구분한다.

**남은 차이·검증 범위:**

- 모든 로그의 fitness·soundness 또는 upstream의 구조 동일성은 미보장. Alpha+ formal exact context와 참조 subset attachment는 별도 선택이다.

**실제 함수·모델:** [alpha.discover_alpha](../../../src/pix/case_centric/alpha.py), [alpha.discover_alpha_plus](../../../src/pix/case_centric/alpha.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_alpha.py](../../../tests/case_centric/test_alpha.py)

</details>

### PM-DISC-005

**업무 질문:** 길이 1 loop 등을 처리하는 Alpha+ 모델은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_petri_net_alpha_plus`

**참조 선택지:** `ALPHA_VERSION_PLUS`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 활동 이름·순서 해석.

**검토 대상 결과:** 길이 1 loop 처리 등을 반영한 Alpha+ Petri net과 초기/최종 marking.

**PIX 계산 정의:**

- classic 및 Alpha+의 causal maximal pair와 short-loop 복원. loop_attachment exact/containing을 구분한다.

**남은 차이·검증 범위:**

- 모든 로그의 fitness·soundness 또는 upstream의 구조 동일성은 미보장. Alpha+ formal exact context와 참조 subset attachment는 별도 선택이다.

**실제 함수·모델:** [alpha.discover_alpha](../../../src/pix/case_centric/alpha.py), [alpha.discover_alpha_plus](../../../src/pix/case_centric/alpha.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_alpha.py](../../../tests/case_centric/test_alpha.py)

</details>

## CC-HEURISTICS

**Classic and Heuristics++**

### PM-DISC-006

**업무 질문:** Dependency와 AND threshold로 잡음을 제어한 Heuristics net은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_heuristics_net`, `pm4py.discovery.discover_petri_net_heuristics`, `pm4py.algo.discovery.heuristics.algorithm.apply_heu`, `pm4py.algo.discovery.heuristics.algorithm.apply_heu_dfg`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동·case·시각이 있는 로그 또는 DFG·활동/경계 빈도와 dependency·AND·빈도 threshold.

**검토 대상 결과:** Heuristics net 또는 이를 변환한 Petri net·초기/최종 marking.

**PIX 계산 정의:**

- classic dependency/AND/short-loop 및 plusplus 명시 구간 중첩으로 HeuristicsNet과 maximal-clique binding을 계산한다.

**남은 차이·검증 범위:**

- Native HeuristicsNet and obligation-token PN converter both exist; selected binding completeness, loop/AND/default threshold and interval annotation policies remain distinct from full upstream behavior. No soundness guarantee follows from conversion.

**실제 함수·모델:** [heuristics.discover_heuristics](../../../src/pix/case_centric/heuristics.py), [heuristics_conversion.heuristics_to_petri_net](../../../src/pix/case_centric/heuristics_conversion.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_heuristics.py](../../../tests/case_centric/test_heuristics.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)

</details>

### PM-DISC-007

**업무 질문:** Heuristics++의 빈도·성능·동시성 정의에 따른 발견 결과는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.heuristics.algorithm.apply_heu`

**참조 선택지:** `PLUSPLUS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동·case·시작/완료 시각이 있는 로그와 Heuristics++ threshold.

**검토 대상 결과:** Heuristics++ 정의로 계산한 결합·동시성 정보가 있는 net과 선택한 변환 모델.

**PIX 계산 정의:**

- classic dependency/AND/short-loop 및 plusplus 명시 구간 중첩으로 HeuristicsNet과 maximal-clique binding을 계산한다.

**남은 차이·검증 범위:**

- Native HeuristicsNet and obligation-token PN converter both exist; selected binding completeness, loop/AND/default threshold and interval annotation policies remain distinct from full upstream behavior. No soundness guarantee follows from conversion.

**실제 함수·모델:** [heuristics.discover_heuristics](../../../src/pix/case_centric/heuristics.py), [heuristics_conversion.heuristics_to_petri_net](../../../src/pix/case_centric/heuristics_conversion.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_heuristics.py](../../../tests/case_centric/test_heuristics.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)

</details>

## CC-ILP

**Region ILP miner**

### PM-DISC-008

**업무 질문:** Trace를 설명하는 region 기반 ILP 모델은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_petri_net_ilp`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 causal 관계·제약·목적함수 설정.

**검토 대상 결과:** Region 제약에서 구성한 Petri net과 초기/최종 marking.

**PIX 계산 정의:**

- 유한 정수 region을 전수 열거하고 separable prefix-extension의 최소 arc-weight cover를 정확히 구한다.

**남은 차이·검증 범위:**

- PM4Py causal-pair ILP 목적함수·무제한 region/MILP formulation을 구현한 것이 아니다. 유한 domain과 탐색 한도를 벗어나면 완료를 주장하지 않는다.

**실제 함수·모델:** [extended_discovery.discover_regions](../../../src/pix/case_centric/extended_discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_extended_discovery.py](../../../tests/case_centric/test_extended_discovery.py)

</details>

## CC-GENETIC

**Genetic miner**

### PM-DISC-009

**업무 질문:** 후보 모델을 진화시키며 fitness 기반으로 선택한 모델은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_petri_net_genetic`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 집단 크기·변이/선택·평가·seed·종료 설정.

**검토 대상 결과:** 선택된 genetic 모델 또는 Petri net·marking과 해당 탐색의 평가 결과.

**PIX 계산 정의:**

- pix.genetic.finite_tree.v1: 실제 population·tournament·elitism·crossover·mutation과 유한 언어 목적함수.

**남은 차이·검증 범위:**

- PM4Py GeneticMatrix/replay objective·무한 loop genotype 및 전역 최적 보장은 없다.

**실제 함수·모델:** [genetic_miner.discover_genetic](../../../src/pix/case_centric/genetic_miner.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_genetic_miner.py](../../../tests/case_centric/test_genetic_miner.py)

</details>

## CC-POWL

**POWL discovery variants**

### PM-DISC-010

**업무 질문:** 부분순서를 표현하는 POWL 모델은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_powl`, `pm4py.algo.discovery.powl.algorithm.get_variant`

**참조 선택지:** `TREE`, `BRUTE_FORCE`, `MAXIMAL`, `DYNAMIC_CLUSTERING`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 빈도가 있는 활동열과 POWL 발견 변형·filtering 설정.

**검토 대상 결과:** 부분순서·choice·loop를 표현하는 POWL 모델.

**PIX 계산 정의:**

- exact_variants / observed_order로 실제 strict-partial-order POWL 모델과 accepting net을 만든다.

**남은 차이·검증 범위:**

- PM4Py TREE/BRUTE_FORCE/MAXIMAL/DYNAMIC_CLUSTERING의 발견 정의를 동일하게 구현한 것은 아니다. 이후 choice-graph 확장도 별도다.

**실제 함수·모델:** [powl.discover_powl](../../../src/pix/case_centric/powl.py), [powl.powl_to_petri_net](../../../src/pix/case_centric/powl.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)

</details>

## CC-SPLIT

**Classic Split and SM2**

### PM-DISC-011

**업무 질문:** 빈도 필터와 동시성 판단에서 classic Split Miner BPMN을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_bpmn_split_miner`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 로그 또는 사전 집계 DFG와 빈도·동시성·OR 처리 설정.

**검토 대상 결과:** Classic Split Miner가 발견한 BPMN 모델.

**PIX 계산 정의:**

- classic_bounded / interval_bounded: frequency filtering·구간 cover/overlap·local XOR/AND decomposition으로 BPMN을 생성한다.

**남은 차이·검증 범위:**

- Classic/SM2 전범위, RPST/SESE OR-join 및 같은 라벨의 동시 구간은 미지원. 입력 구간은 이미 짝지어져 있어야 한다.

**실제 함수·모델:** [split_miner.discover_split_miner](../../../src/pix/case_centric/split_miner.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_split_miner.py](../../../tests/case_centric/test_split_miner.py)

</details>

### PM-DISC-012

**업무 질문:** Lifecycle 구간 겹침을 활용한 Split Miner 2 BPMN은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.split_miner.algorithm.apply`

**참조 선택지:** `SM2`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case·활동·lifecycle·시각이 있는 로그와 동시성 임계값.

**검토 대상 결과:** Complete-event DFG와 구간 겹침을 반영한 SM2 BPMN 모델.

**PIX 계산 정의:**

- classic_bounded / interval_bounded: frequency filtering·구간 cover/overlap·local XOR/AND decomposition으로 BPMN을 생성한다.

**남은 차이·검증 범위:**

- Classic/SM2 전범위, RPST/SESE OR-join 및 같은 라벨의 동시 구간은 미지원. 입력 구간은 이미 짝지어져 있어야 한다.

**실제 함수·모델:** [split_miner.discover_split_miner](../../../src/pix/case_centric/split_miner.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_split_miner.py](../../../tests/case_centric/test_split_miner.py)

</details>

## CC-FOOTPRINTS

**Log/model footprints and conformance**

### PM-DISC-014

**업무 질문:** 로그 또는 모델에서 순서·병렬·시작·종료 footprints를 추출할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_footprints`

**참조 선택지:** `ENTIRE_EVENT_LOG`, `ENTIRE_DATAFRAME`, `TRACE_BY_TRACE`, `PETRI_REACH_GRAPH`, `PROCESS_TREE`, `POWL`, `DFG`, `POLARS_LAZYFRAMES`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·trace·DFG 또는 Petri net/marking·tree·POWL과 선택한 해석 범위.

**검토 대상 결과:** 순서·병렬·활동·시작/종료 등의 footprints를 전체 또는 trace별로 표현한 관계 집합.

**PIX 계산 정의:**

- source adjacency에서 log footprint causal/symmetric/unrelated·boundary·minimum length를 계산한다.
- New model footprints: reachable versus accepting behavior on PN or converted process tree; commuting transitions reported separately.

**남은 차이·검증 범위:**

- PN/tree source implementation and corresponding tests are present. POWL/DFG specialized footprints and all upstream backend definitions remain uncovered; observed symmetric adjacency is not actual concurrency.

**실제 함수·모델:** [discovery.discover_footprints](../../../src/pix/case_centric/discovery.py), [model_discovery.discover_model_footprints](../../../src/pix/case_centric/model_discovery.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)
- [tests/case_centric/test_model_discovery.py](../../../tests/case_centric/test_model_discovery.py)

</details>

### PM-CONF-020

**업무 질문:** 로그와 모델의 footprints 위반·fitness·precision은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_diagnostics_footprints`, `pm4py.conformance.fitness_footprints`, `pm4py.conformance.precision_footprints`

**참조 선택지:** `LOG_MODEL`, `LOG_EXTENSIVE`, `TRACE_EXTENSIVE`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그/trace footprints와 모델 footprints 및 비교 범위.

**검토 대상 결과:** 위반 관계·경계·길이 진단과 footprints fitness·precision.

**PIX 계산 정의:**

- 관측/모델 footprint의 관계·활동·경계·minimum-length 포함 검사와 relation-type ratio.

**남은 차이·검증 범위:**

- Alignment/ET precision이 아니며 LOG_MODEL/LOG_EXTENSIVE/TRACE_EXTENSIVE의 모든 weighting 동일성은 미검증.

**실제 함수·모델:** [declarative.check_footprints](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

## CC-CAUSAL

**Alpha/heuristics causal relation**

### PM-DISC-015

**업무 질문:** DFG에서 Alpha 또는 Heuristics 방식의 causal 관계를 얻을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.causal.algorithm.apply`

**참조 선택지:** `CAUSAL_ALPHA`, `CAUSAL_HEURISTIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동쌍 빈도가 있는 DFG와 causal 계산 방식.

**검토 대상 결과:** Alpha 또는 Heuristics 정의의 방향성 인과 관계와 해당 가중치.

**PIX 계산 정의:**

- Alpha 발견 중 causal 관계가 실제 계산되어 증거에 보존된다.

**남은 차이·검증 범위:**

- DFG→causal relation 독립 진입점과 CAUSAL_HEURISTIC의 동일 반환 정의는 미구현이다.

**실제 함수·모델:** [alpha.discover_alpha](../../../src/pix/case_centric/alpha.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_alpha.py](../../../tests/case_centric/test_alpha.py)

</details>

## CC-STATE-VIEWS

**View-based state transition system and prefix trie**

### PM-DISC-016

**업무 질문:** 과거·미래의 제한된 관측 창으로 어떤 상태 전이가 보이는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_transition_system`

**참조 선택지:** `VIEW_BASED`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 forward/backward 방향·window 크기·sequence/set/multiset 해석.

**검토 대상 결과:** 추상화한 관측 상태와 활동 전이로 구성한 transition system.

**PIX 계산 정의:**

- past/future window와 sequence/set/multiset context별 transition system.

**남은 차이·검증 범위:**

- 상태 추상화가 다른 모델은 동일 모델이 아니다. 모든 upstream option/backend 동등성은 미검증.

**실제 함수·모델:** [discovery.discover_transition_system](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

### PM-DISC-017

**업무 질문:** 관측 prefix를 공유하는 trie를 만들 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_prefix_tree`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 활동 classifier.

**검토 대상 결과:** 공통 prefix를 공유하고 trace 종료를 표현하는 trie.

**PIX 계산 정의:**

- 중복 case 빈도와 epsilon acceptance를 보존한 prefix trie. 두 참조 행은 한 계산을 공유한다.

**남은 차이·검증 범위:**

- 한도에서 완료된 전체 trie처럼 표시하지 않는다. 그래프 표현의 구조 동일성·모든 upstream 옵션은 미검증.

**실제 함수·모델:** [discovery.discover_prefix_tree](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

### PM-DATA-041

**업무 질문:** 활동열의 공통 prefix를 trie 구조로 표현할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.log_to_trie.algorithm.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 activity key·max path length.

**검토 대상 결과:** 공통 prefix를 공유하는 trie와 terminal/중복 관측 근거.

**PIX 계산 정의:**

- 중복 case 빈도와 epsilon acceptance를 보존한 prefix trie. 두 참조 행은 한 계산을 공유한다.

**남은 차이·검증 범위:**

- 한도에서 완료된 전체 trie처럼 표시하지 않는다. 그래프 표현의 구조 동일성·모든 upstream 옵션은 미검증.

**실제 함수·모델:** [discovery.discover_prefix_tree](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

## CC-TEMPORAL-PROFILE

**Temporal profile discovery and diagnosis**

### PM-DISC-018

**업무 질문:** 활동 쌍의 시간 관계에서 정상 범위 temporal profile을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_temporal_profile`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동·시각과 시간차·업무시간 해석 설정.

**검토 대상 결과:** 활동쌍별 관측 시간차의 평균·표준편차를 담은 temporal profile.

**PIX 계산 정의:**

- ordered occurrence pair 또는 DFG pair의 completion→start 시간 평균·분산과 범위 위반을 계산한다.

**남은 차이·검증 범위:**

- PIX 기본 ddof=0, 명시 ddof=1 singleton unknown; 참조 default sample/singleton-zero와 다름. missing/negative/unprofiled 처리는 명시 profile로 남긴다.

**실제 함수·모델:** [declarative.check_temporal_profile](../../../src/pix/case_centric/declarative.py), [declarative.discover_temporal_profile](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

### PM-CONF-021

**업무 질문:** 발견한 temporal profile의 정상 시간 범위를 벗어난 사례는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_temporal_profile`, `pm4py.algo.conformance.temporal_profile.algorithm.get_diagnostics_dataframe`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 시각이 있는 case 로그·temporal profile과 허용 표준편차 배수.

**검토 대상 결과:** 정상 시간 범위를 벗어난 활동쌍·case·관측 시간차와 편차 진단.

**PIX 계산 정의:**

- ordered occurrence pair 또는 DFG pair의 completion→start 시간 평균·분산과 범위 위반을 계산한다.

**남은 차이·검증 범위:**

- PIX 기본 ddof=0, 명시 ddof=1 singleton unknown; 참조 default sample/singleton-zero와 다름. missing/negative/unprofiled 처리는 명시 profile로 남긴다.

**실제 함수·모델:** [declarative.check_temporal_profile](../../../src/pix/case_centric/declarative.py), [declarative.discover_temporal_profile](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

## CC-LOG-SKELETON

**Log skeleton discovery and conformance**

### PM-DISC-019

**업무 질문:** 반복·선후·동시 출현 규칙의 log skeleton을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_log_skeleton`, `pm4py.algo.discovery.log_skeleton.algorithm.apply_from_variants_list`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 noise threshold.

**검토 대상 결과:** 선후·동시 출현·활동 빈도 규칙을 모은 log skeleton 모델.

**PIX 계산 정의:**

- equivalence/always-after/before/never-together/directly-follows/count-domain을 occurrence별 검사한다.

**남은 차이·검증 범위:**

- 참조 일부 occurrence/case 혼합 분모와 한 occurrence만 만족해도 허용하는 경로를 재현하지 않는다. A,B,A의 always-after(A,B)는 위반이다.

**실제 함수·모델:** [declarative.check_log_skeleton](../../../src/pix/case_centric/declarative.py), [declarative.discover_log_skeleton](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

### PM-CONF-023

**업무 질문:** Log skeleton 규칙을 어긴 case와 항목은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_log_skeleton`, `pm4py.algo.conformance.log_skeleton.algorithm.apply_from_variants_list`, `pm4py.algo.conformance.log_skeleton.algorithm.get_diagnostics_dataframe`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열·log skeleton 모델과 평가 설정.

**검토 대상 결과:** Case별 skeleton 위반 항목·적합 여부 및 집계 진단.

**PIX 계산 정의:**

- equivalence/always-after/before/never-together/directly-follows/count-domain을 occurrence별 검사한다.

**남은 차이·검증 범위:**

- 참조 일부 occurrence/case 혼합 분모와 한 occurrence만 만족해도 허용하는 경로를 재현하지 않는다. A,B,A의 always-after(A,B)는 위반이다.

**실제 함수·모델:** [declarative.check_log_skeleton](../../../src/pix/case_centric/declarative.py), [declarative.discover_log_skeleton](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

## CC-DECLARE

**Declare discovery, evaluation and finite playout**

### PM-DISC-020

**업무 질문:** Support·confidence 조건을 만족하는 Declare 규칙은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_declare`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 후보 template·활동·support/confidence 설정.

**검토 대상 결과:** 선택 기준을 만족하는 Declare 규칙과 규칙별 support·confidence.

**PIX 계산 정의:**

- 22 canonical template, activation-case support와 conditional confidence, 모든 activation witness 및 open pending/violation.

**남은 차이·검증 범위:**

- 참조 negative succession을 positive succession의 논리 부정으로 계산하는 동작과 다르다. candidate projection·vacuity·분모가 같다는 주장은 없다.

**실제 함수·모델:** [declarative.check_declare](../../../src/pix/case_centric/declarative.py), [declarative.discover_declare](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

### PM-CONF-022

**업무 질문:** Declare 규칙을 만족하거나 위반한 trace와 activation은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_declare`, `pm4py.algo.conformance.declare.algorithm.get_diagnostics_dataframe`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열 또는 명시한 객체 trace·Declare 규칙과 관측 종료 조건.

**검토 대상 결과:** Trace별 규칙 위반·충족 진단과 적용 template의 적합성 정보.

**PIX 계산 정의:**

- 22 canonical template, activation-case support와 conditional confidence, 모든 activation witness 및 open pending/violation.

**남은 차이·검증 범위:**

- 참조 negative succession을 positive succession의 논리 부정으로 계산하는 동작과 다르다. candidate projection·vacuity·분모가 같다는 주장은 없다.

**실제 함수·모델:** [declarative.check_declare](../../../src/pix/case_centric/declarative.py), [declarative.discover_declare](../../../src/pix/case_centric/declarative.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative.py](../../../tests/case_centric/test_declarative.py)

</details>

### PM-SIM-006

**업무 질문:** Declare 규칙을 만족하는 유한 trace를 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.simulation.playout.declare.algorithm.apply`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Declare 규칙 모델과 활동 집합·trace 길이/수량 제한.

**검토 대상 결과:** 규칙을 만족하도록 생성한 유한 trace 로그.

**PIX 계산 정의:**

- 22 finite-trace templates; bounded exhaustive language and seeded rejection playout with known proposal distribution.

**남은 차이·검증 범위:**

- Bounded length language only; satisfying words of different lengths are not equiprobable. No synthetic timestamped log or upstream sampling-distribution parity.

**실제 함수·모델:** [declarative_simulation.generate_declare_language](../../../src/pix/case_centric/declarative_simulation.py), [declarative_simulation.play_out_declare](../../../src/pix/case_centric/declarative_simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_declarative_simulation.py](../../../tests/case_centric/test_declarative_simulation.py)

</details>

## CC-BATCHES

**Batch recognition**

### PM-DISC-021

**업무 질문:** 활동·자원·시간 구간에서 어떤 작업이 batch로 묶이는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_batches`

**참조 선택지:** `LOG`, `PANDAS`, `POLARS`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case·활동·자원·시작/완료 시각과 batch 간격·크기 기준.

**검토 대상 결과:** 활동·자원별 batch 구간·유형 및 참여 이벤트 집단.

**PIX 계산 정의:**

- 활동·자원별 실제 구간 component와 simultaneous/start/end/sequential/residual concurrent 분류.

**남은 차이·검증 범위:**

- positive merge gap의 residual concurrent는 중첩 증명이 아니다. missing start/resource는 생성하지 않으며 모든 backend 동등성은 미검증.

**실제 함수·모델:** [discovery.discover_batches](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

## CC-CORRELATION

**Correlation mining without trusted case linkage**

### PM-DISC-022

**업무 질문:** Case 식별이 불충분한 이벤트로부터 활동 간 흐름을 추정할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.correlation_miner`

**참조 선택지:** `CLASSIC`, `CLASSIC_SPLIT`, `TRACE_BASED`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동·시각이 있는 이벤트와 선택적으로 case 정보, correlation 변형 설정.

**검토 대상 결과:** 관측의 상관 관계로 추정한 DFG 빈도와 활동쌍 시간 정보.

**PIX 계산 정의:**

- Exact rational balanced transportation with classic pooling, explicit chunks and supplied-case grouping.

**남은 차이·검증 범위:**

- Native source and corresponding tests are present; independent reference-result equivalence remains unestablished. Estimated flows are not observed DFG or reconstructed case identities. Cost/default/chunk profiles not all-reference parity.

**실제 함수·모델:** [correlation.discover_correlation](../../../src/pix/case_centric/correlation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/test_correlation.py](../../../tests/test_correlation.py)

</details>

## CC-LOCAL-MODELS

**Local process model discovery and evaluation**

### PM-DISC-023

**업무 질문:** 전체 모델 대신 자주 반복되는 국소 프로세스 모델과 품질을 찾을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.local_process_models.algorithm.find_local_process_models`, `pm4py.algo.discovery.local_process_models.metrics.quality_metrics.evaluate_tree`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 후보 활동·모델 크기·탐색/품질 기준.

**검토 대상 결과:** 발견된 local process tree 목록과 모델별 국소 품질 통계.

**PIX 계산 정의:**

- bounded binary tree 후보의 언어와 projected nonoverlapping occurrence support를 계산한다.

**남은 차이·검증 범위:**

- PM4Py alignment-based LPM quality·전체 후보 동치 제거·무제한 탐색은 미구현. bounded_language_fit과 prefix_determinism은 별도 PIX 지표다.

**실제 함수·모델:** [discovery.discover_local_process_models](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

## CC-DFG

**Frequency/performance/triples/case-attribute DFG**

### PM-DISC-024

**업무 질문:** Case의 활동 순서에서 직접 후속 관계와 시작·종료·빈도를 얻을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_dfg`, `pm4py.discovery.discover_directly_follows_graph`, `pm4py.discovery.discover_dfg_typed`

**참조 선택지:** `NATIVE`, `FREQUENCY`, `FREQUENCY_GREEDY`, `CLEAN`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열 또는 명시한 객체 trace와 순서·classifer 해석.

**검토 대상 결과:** 직접 후속 관계별 빈도와 시작/종료 활동 빈도, 선택한 typed DFG 표현.

**PIX 계산 정의:**

- source adjacency pair 또는 case-presence 빈도, 시작·끝·활동·empty case 집계.

**남은 차이·검증 범위:**

- 참조 backend 정렬·Greedy·CLEAN의 모든 차이를 같은 계산이라고 보지 않는다. Pair budget 결과는 partial lower bound일 수 있다.

**실제 함수·모델:** [discovery.discover_dfg](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

### PM-DISC-025

**업무 질문:** 직접 후속 관계의 소요시간 분포를 계산할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_performance_dfg`

**참조 선택지:** `PERFORMANCE`, `PERFORMANCE_GREEDY`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동 순서·시각과 start/complete·집계·업무시간 설정.

**검토 대상 결과:** 직접 후속 edge별 소요시간 집계와 표본의 의미.

**PIX 계산 정의:**

- variant와 occurrence position별 adjacent completion gap 증거·요약이 계산된다.

**남은 차이·검증 범위:**

- activity-pair performance DFG의 독립 반환형·PERFORMANCE_GREEDY aggregation과 calendar profile은 미구현이다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DISC-026

**업무 질문:** 활동 삼중항과 edge별 case 속성 분포를 계산할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.dfg.algorithm.apply`

**참조 선택지:** `FREQ_TRIPLES`, `CASE_ATTRIBUTES`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열 및 case 속성과 triple/속성 집계 선택.

**검토 대상 결과:** 연속 활동 삼중항 빈도 또는 DFG edge별 case 속성 분포.

**PIX 계산 정의:**

- Consecutive source-position triples and typed case-attribute conditioned DFG; occurrence and distinct-case counts retain witnesses.

**남은 차이·검증 범위:**

- All backend/default/dictionary-key semantics remain unverified. Structured/null/missing attributes follow explicit PIX definitions.

**실제 함수·모델:** [context_discovery.discover_activity_triples](../../../src/pix/case_centric/context_discovery.py), [context_discovery.discover_case_attribute_dfg](../../../src/pix/case_centric/context_discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_context_discovery.py](../../../tests/case_centric/test_context_discovery.py)

</details>

### PM-DATA-001

**업무 질문:** Case별 최초·마지막 활동과 그 빈도는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_start_activities`, `pm4py.stats.get_end_activities`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** CaseLog/TraceSet, activity classifier와 기록 순서, 빈 case 포함 정책.

**검토 대상 결과:** 시작·종료 활동별 case 빈도와 빈 case 수.

**PIX 계산 정의:**

- source adjacency pair 또는 case-presence 빈도, 시작·끝·활동·empty case 집계.

**남은 차이·검증 범위:**

- 참조 backend 정렬·Greedy·CLEAN의 모든 차이를 같은 계산이라고 보지 않는다. Pair budget 결과는 partial lower bound일 수 있다.

**실제 함수·모델:** [discovery.discover_dfg](../../../src/pix/case_centric/discovery.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)

</details>

## CC-REPLAY

**Forward/backward replay and token-based quality**

### PM-CONF-001

**업무 질문:** Trace를 Petri net에 재생할 때 어떤 token이 부족하거나 남는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_diagnostics_token_based_replay`, `pm4py.conformance.replay_prefix_tbr`, `pm4py.algo.conformance.tokenreplay.algorithm.get_diagnostics_dataframe`

**참조 선택지:** `TOKEN_REPLAY`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동열·weighted Petri net·초기/최종 marking과 재생 정책.

**검토 대상 결과:** Trace별 발화·도달 marking·missing/remaining/consumed/produced token 및 재생 진단.

**PIX 계산 정의:**

- 기존 PIX deterministic token replay와 place/transition witness를 재사용한다.

**남은 차이·검증 범위:**

- PM4Py 모든 repair/silent selection/cache/final-token 옵션의 동등성은 미검증. unknown activity는 별도 log deviation이다.

**실제 함수·모델:** [replay.replay_traces](../../../src/pix/compute/replay.py).

**관련 테스트:** registry에 연결된 파일이 없다.

### PM-CONF-002

**업무 질문:** Backward silent 탐색을 사용하는 token replay 결과는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.tokenreplay.algorithm.apply`

**참조 선택지:** `BACKWARDS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동열·Petri net·초기/최종 marking과 backward 재생 설정.

**검토 대상 결과:** Backward 탐색으로 선택한 재생 전이·token 계수·도달 상태와 진단.

**PIX 계산 정의:**

- Native regression of token requirements and reverse weighted final completion; independent from ordinary forward replay.

**남은 차이·검증 범위:**

- PIX shortest/lexical backward silent plan and repair profile; new source/tests need final QA, not PM4Py BACKWARDS numerical parity.

**실제 함수·모델:** [backwards_replay.replay_backwards](../../../src/pix/case_centric/backwards_replay.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_backwards_replay.py](../../../tests/case_centric/test_backwards_replay.py)

</details>

### PM-CONF-013

**업무 질문:** Token 재생의 적합성을 정규화 점수로 비교할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.fitness_token_based_replay`, `pm4py.algo.evaluation.replay_fitness.algorithm.evaluate`

**참조 선택지:** `TOKEN_BASED`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net 또는 동일 정책으로 계산된 token 재생 결과.

**검토 대상 결과:** 적합 trace 비율·trace 평균·token 총계 기반의 정규화 fitness.

**PIX 계산 정의:**

- 초기 production·최종 consumption 포함 token-balance fitness; pooled ratio와 case mean 분리.

**남은 차이·검증 범위:**

- 수식 대응이 replay tie/repair 정책까지 참조와 동일함을 뜻하지 않는다. Token score 1이어도 unknown-label deviation이면 strictly fitting이 아니다.

**실제 함수·모델:** [conformance.measure_token_fitness](../../../src/pix/case_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_conformance.py](../../../tests/case_centric/test_conformance.py)

</details>

### PM-CONF-015

**업무 질문:** Replay 기반 escaping-transitions precision은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.precision_token_based_replay`

**참조 선택지:** `ETCONFORMANCE_TOKEN`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net과 replay·prefix 가중치·enabled 해석.

**검토 대상 결과:** 재생 가능한 prefix의 escaping transition에 근거한 ET precision.

**PIX 계산 정의:**

- method=token: deterministic no-repair prefix와 silent closure의 frequency-weighted escaping-label 비율.

**남은 차이·검증 범위:**

- Unfit prefix·zero denominator는 unknown/coverage로 드러낸다. 참조 zero→1 fallback이나 모든 token replay 선택과 동등하지 않다.

**실제 함수·모델:** [conformance.measure_et_precision](../../../src/pix/case_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_conformance.py](../../../tests/case_centric/test_conformance.py)

</details>

### PM-CONF-018

**업무 질문:** 전이 방문 빈도에서 generalization을 계산할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.generalization_tbr`

**참조 선택지:** `GENERALIZATION_TOKEN`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net과 token 재생 결과 또는 설정.

**검토 대상 결과:** 모델 전이의 방문 빈도·미방문 처리에 근거한 generalization 점수.

**PIX 계산 정의:**

- 모든 transition ID의 방문 수로 1-mean(1/sqrt(n)); 미방문 penalty 1, silent 포함.

**남은 차이·검증 범위:**

- 재생 선택/수리 결과가 다르면 score가 달라진다. 보지 못한 실제 미래 행동에 대한 보장은 아니다.

**실제 함수·모델:** [conformance.measure_token_generalization](../../../src/pix/case_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_conformance.py](../../../tests/case_centric/test_conformance.py)

</details>

## CC-ALIGNMENT

**Petri-net exact/discounted/approximate/decomposed alignment and normalized quality**

### PM-CONF-003

**업무 질문:** Trace와 accepting Petri net 사이의 최소 비용 alignment는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_diagnostics_alignments`, `pm4py.algo.conformance.alignments.petri_net.algorithm.apply_trace`, `pm4py.algo.conformance.alignments.petri_net.algorithm.apply_log`, `pm4py.algo.conformance.alignments.petri_net.algorithm.apply_multiprocessing` 외 1개(전체는 registry)

**참조 선택지:** `VERSION_DIJKSTRA_NO_HEURISTICS`, `VERSION_DIJKSTRA_LESS_MEMORY`, `VERSION_DIJKSTRA_SEMANTICS`, `VERSION_STATE_EQUATION_A_STAR`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace 또는 로그·accepting Petri net·이동 비용과 탐색 한도.

**검토 대상 결과:** 최소 비용 log/model/synchronous 이동열·최종 상태와 최적성/탐색 완료 정보.

**PIX 계산 정의:**

- 기존 Dijkstra와 별개로 synchronous-product LP relaxation의 rational-certified bound를 쓰는 native A*가 있다.

**남은 차이·검증 범위:**

- 모든 PM4Py Dijkstra variant의 메모리 전략·tie·cost option 동등성과 참조 전체 A* parity는 미검증. solver 검증은 별도 근거를 따른다.

**실제 함수·모델:** [alignment_search.align_state_equation_astar](../../../src/pix/case_centric/alignment_search.py), [conformance.align_traces](../../../src/pix/compute/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_alignment_search.py](../../../tests/case_centric/test_alignment_search.py)

</details>

### PM-CONF-004

**업무 질문:** Discounted edit 비용을 쓰는 Petri net alignment는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.petri_net.algorithm.apply`

**참조 선택지:** `VERSION_DISCOUNTED_A_STAR`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace·Petri net·초기/최종 marking과 discount 비용 설정.

**검토 대상 결과:** Discounted 목적함수에 따른 alignment 이동열·비용·탐색 결과.

**PIX 계산 정의:**

- 명시 finite horizon과 exact rational discount 비용의 alignment 탐색.

**남은 차이·검증 범위:**

- 참조 discounted objective·길이 정규화·unbounded search의 동일성은 미검증. horizon 밖 optimum은 주장하지 않는다.

**실제 함수·모델:** [alignment_search.align_discounted_astar](../../../src/pix/case_centric/alignment_search.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_alignment_search.py](../../../tests/case_centric/test_alignment_search.py)

</details>

### PM-CONF-005

**업무 질문:** 큰 trace에서 근사 alignment를 계산하고 오차·완료 범위를 설명할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.petri_net.algorithm.apply`

**참조 선택지:** `APPROX_TANDEM_REPEATS`, `APPROX_SLIDING_WINDOW`, `APPROX_FIXED_HORIZON`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace·Petri net·초기/최종 marking과 반복 축약/window/horizon 설정.

**검토 대상 결과:** 선택한 근사법의 alignment·비용과 적용 가능한 경계·완료 정보.

**PIX 계산 정의:**

- Distinct tandem reduction, top-k marking beam over sliding windows, and fixed-horizon integer-tail strategies with validated executable alignment witnesses.

**남은 차이·검증 범위:**

- Reference variant parity and approximation error guarantees remain unverified. Feasible complete witness is an upper bound; exact fallback or verification must be explicit, not inferred from a finite limit.

**실제 함수·모델:** [approximate_alignment.align_fixed_horizon](../../../src/pix/case_centric/approximate_alignment.py), [approximate_alignment.align_sliding_window](../../../src/pix/case_centric/approximate_alignment.py), [approximate_alignment.align_tandem_repeats](../../../src/pix/case_centric/approximate_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_approximate_alignment.py](../../../tests/case_centric/test_approximate_alignment.py)

</details>

### PM-CONF-006

**업무 질문:** 분해한 Petri net을 조합해 alignment를 구할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.decomposed.algorithm.apply`

**참조 선택지:** `RECOMPOS_MAXIMAL`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·Petri net·초기/최종 marking과 분해/재조합 설정.

**검토 대상 결과:** 재조합한 alignment·비용과 각 구성요소 계산을 연결한 결과.

**PIX 계산 정의:**

- independent weak components와 event allocation을 이용한 분해 alignment.

**남은 차이·검증 범위:**

- PM4Py maximal decomposition과 RECOMPOS_MAXIMAL의 일반 공유 전이 재조합 의미는 별도 잔여다.

**실제 함수·모델:** [decomposed_alignment.align_decomposed](../../../src/pix/case_centric/decomposed_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_decomposed_alignment.py](../../../tests/case_centric/test_decomposed_alignment.py)

</details>

### PM-CONF-014

**업무 질문:** 최적 alignment 비용을 기준 경로 비용으로 정규화할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.fitness_alignments`, `pm4py.algo.evaluation.replay_fitness.algorithm.evaluate`

**참조 선택지:** `ALIGNMENT_BASED`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net·alignment 비용과 모델 최소 완주 기준 비용.

**검토 대상 결과:** Trace 평균·전체 합계 기반 정규화 alignment fitness와 적합 비율.

**PIX 계산 정의:**

- 1-cost/(log deletion cost + shortest empty-trace model completion cost), pooled/case-mean 분리.

**남은 차이·검증 범위:**

- 정규화 경로 탐색이 끝나지 않으면 전체 score를 제공하지 않는다. 참조 default cost/tie와 전옵션 동등성은 미검증.

**실제 함수·모델:** [conformance.measure_alignment_fitness](../../../src/pix/case_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_conformance.py](../../../tests/case_centric/test_conformance.py)

</details>

### PM-CONF-016

**업무 질문:** Alignment 기반 ET precision과 alignment 후 automaton precision은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.precision_alignments`

**참조 선택지:** `ALIGN_ETCONFORMANCE`, `AUTOMATON_AFTER_ALIGN`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net과 alignment·prefix/automaton precision 설정.

**검토 대상 결과:** Alignment 기반 ET precision 또는 정렬된 모델 실행 automaton 기반 precision.

**PIX 계산 정의:**

- Native optimal alignment의 model-side projected automaton과 실제 도달 marking에서 precision을 계산한다. Raw-prefix ET는 별도 함수다.

**남은 차이·검증 범위:**

- Tie 선택·cost·duplicate-label symbol_mode가 명시된다. 참조 automaton helper와 전체 동작 parity는 미검증.

**실제 함수·모델:** [advanced_precision.measure_automaton_precision](../../../src/pix/case_centric/advanced_precision.py), [conformance.measure_et_precision](../../../src/pix/case_centric/conformance.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_advanced_precision.py](../../../tests/case_centric/test_advanced_precision.py)
- [tests/case_centric/test_conformance.py](../../../tests/case_centric/test_conformance.py)

</details>

### PM-CONF-024

**업무 질문:** 단일 trace가 tree 또는 Petri net에 적합한지 판정할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.check_is_fitting`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 단일 활동열과 process tree 또는 Petri net·초기/최종 marking.

**검토 대상 결과:** 선택한 적합성 정의에 따른 적합 판정과 평가 한도 상태.

**PIX 계산 정의:**

- Native alignment의 완료·비용·최종 marking 증거로 적합 여부를 판단할 수 있다.

**남은 차이·검증 범위:**

- 독립 check_is_fitting wrapper와 모든 tree/net input dispatch는 미구현. 완료되지 않은 탐색을 false로 바꾸지 않는다.

**실제 함수·모델:** [conformance.measure_alignment_fitness](../../../src/pix/case_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_conformance.py](../../../tests/case_centric/test_conformance.py)

</details>

## CC-TREE-ALIGNMENT

**Process-tree search/DP/MILP/approximate alignment**

### PM-CONF-007

**업무 질문:** Process tree 자체에 대한 정확·근사 alignment는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.process_tree.algorithm.apply`

**참조 선택지:** `APPROXIMATED_ORIGINAL`, `SEARCH_GRAPH_PT`, `DYNAMIC_PROGRAMMING`, `MILP`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace 또는 로그·process tree와 비용·직접 tree 탐색 변형.

**검토 대상 결과:** Tree 의미에 맞춘 alignment·비용과 정확/근사·탐색 상태.

**PIX 계산 정의:**

- Direct compositional occurrence-sensitive sequence/XOR/parallel/loop dynamic programming; no PN conversion.

**남은 차이·검증 범위:**

- New source/tests need final QA. PM SEARCH_GRAPH_PT/MILP/APPROXIMATED_ORIGINAL and all DP cost/tie definitions remain separate.

**실제 함수·모델:** [tree_alignment.align_process_tree_dp](../../../src/pix/case_centric/tree_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_tree_alignment.py](../../../tests/case_centric/test_tree_alignment.py)

</details>

## CC-DFG-ALIGNMENT

**DFG alignment and DFG precision**

### PM-CONF-008

**업무 질문:** DFG가 허용하는 경로와 trace의 alignment는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.dfg.algorithm.apply`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace·DFG·시작/종료 활동과 이동 비용.

**검토 대상 결과:** DFG 허용 경로에 대한 alignment 이동열과 비용.

**PIX 계산 정의:**

- 명시 start/end/empty-word를 가진 DFG와 trace의 weighted product Dijkstra.

**남은 차이·검증 범위:**

- DFG는 token·concurrency 모델이 아니다. 참조 cost/default/tie 전옵션 동등성은 미검증.

**실제 함수·모델:** [sequence_alignment.align_dfg](../../../src/pix/case_centric/sequence_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_sequence_alignment.py](../../../tests/case_centric/test_sequence_alignment.py)

</details>

### PM-CONF-017

**업무 질문:** DFG가 허용한 다음 행동 중 관측되지 않은 비율은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.evaluation.precision.dfg.algorithm.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그 활동열·DFG·시작/종료 활동.

**검토 대상 결과:** 허용 prefix에서 관측하지 않은 다음 활동에 근거한 DFG precision.

**PIX 계산 정의:**

- 관측 strict prefix와 DFG의 enabled outgoing labels의 occurrence-weighted escaping 비율.

**남은 차이·검증 범위:**

- Raw-prefix 지표이며 alignment/termination scoring이 아니다. zero denominator·unsupported prefix에서 참조 fallback과 차이가 있다.

**실제 함수·모델:** [advanced_precision.measure_dfg_precision](../../../src/pix/case_centric/advanced_precision.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_advanced_precision.py](../../../tests/case_centric/test_advanced_precision.py)

</details>

## CC-LANGUAGE-ALIGNMENT

**Log-to-log edit alignment**

### PM-CONF-009

**업무 질문:** Trace를 다른 관측 언어와 비교한 edit-distance alignment는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.edit_distance.algorithm.apply`

**참조 선택지:** `EDIT_DISTANCE`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 비교할 trace 집합과 기준 로그의 활동열 집합, edit 비용.

**검토 대상 결과:** 기준 활동열에 대한 최소 편집 alignment와 비용.

**PIX 계산 정의:**

- Insertion/deletion/substitution weighted DP, nearest reference case의 모든 동점과 edit witness.

**남은 차이·검증 범위:**

- Delimiter나 backend 표현 호환은 별도다. 계산은 명시된 비용·DP budget 내에만 exact이다.

**실제 함수·모델:** [sequence_alignment.align_log_to_log](../../../src/pix/case_centric/sequence_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_sequence_alignment.py](../../../tests/case_centric/test_sequence_alignment.py)

</details>

## CC-CONFORMANCE-APPROX

**Variant subset approximation with bounds**

### PM-CONF-010

**업무 질문:** 대표 variant 부분집합으로 conformance를 근사하고 집계 경계를 줄 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.alignments.edit_distance.variants.approx_subset.apply_with_summary`, `pm4py.algo.conformance.alignments.edit_distance.algorithm.apply_approximation`, `pm4py.algo.conformance.alignments.edit_distance.algorithm.apply_approximation_with_summary`

**참조 선택지:** `APPROX_SUBSET`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net과 대표 부분집합 선택·seed·근사 설정.

**검토 대상 결과:** 대표 활동열에서 복원한 alignment와 근사 적합성·집계 경계.

**PIX 계산 정의:**

- Representative observed variants or simulated accepted runs; exact selected alignments plus edit-distance derived executable witnesses and certified unit-visible/zero-silent cost intervals.

**남은 차이·검증 범위:**

- No full PM APPROX_SUBSET tie/default/positive-silent-cost parity. Fitness intervals require exact shortest accepted model-word length; incomplete representatives and normalization retain coverage gaps.

**실제 함수·모델:** [conformance_approximation.approximate_conformance](../../../src/pix/case_centric/conformance_approximation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_conformance_approximation.py](../../../tests/case_centric/test_conformance_approximation.py)

</details>

## CC-ANTI-ALIGNMENT

**Anti-alignment and associated precision**

### PM-CONF-011

**업무 질문:** 로그에서 가장 멀리 떨어진 허용 행동과 anti-alignment precision은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.antialignments.algorithm.apply_log`

**참조 선택지:** `VERSION_DISCOUNTED_A_STAR`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그의 활동열 집합·accepting Petri net과 discount·epsilon·탐색 한도.

**검토 대상 결과:** 관측에서 먼 허용 실행인 anti-alignment와 거리·precision 경계.

**PIX 계산 정의:**

- 실제 weighted Petri net의 유한 visible horizon 언어에서 anti max-min 및 multi sum-distance 목적함수를 계산한다.

**남은 차이·검증 범위:**

- 참조 discounted/length-normalized 목표 및 anti-alignment precision은 미구현. Multi sum objective를 minimax와 혼동하지 않는다. horizon·state·DP 한도는 결과에 남긴다.

**실제 함수·모델:** [pn_language_alignment.bounded_petri_net_anti_alignment](../../../src/pix/case_centric/pn_language_alignment.py), [pn_language_alignment.bounded_petri_net_multi_alignment](../../../src/pix/case_centric/pn_language_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_pn_language_alignment.py](../../../tests/case_centric/test_pn_language_alignment.py)

</details>

## CC-MULTI-ALIGNMENT

**Multi-alignment representative model behavior**

### PM-CONF-012

**업무 질문:** 여러 trace를 대표하도록 최대 거리를 줄이는 모델 행동은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.conformance.multialignments.algorithm.apply_log`

**참조 선택지:** `VERSION_DISCOUNTED_A_STAR`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그의 활동열 집합·accepting Petri net과 discounted 거리·탐색 한도.

**검토 대상 결과:** 여러 trace에 대한 최대 거리를 줄이는 대표 모델 실행과 그 거리.

**PIX 계산 정의:**

- 실제 weighted Petri net의 유한 visible horizon 언어에서 anti max-min 및 multi sum-distance 목적함수를 계산한다.

**남은 차이·검증 범위:**

- 참조 discounted/length-normalized 목표 및 anti-alignment precision은 미구현. Multi sum objective를 minimax와 혼동하지 않는다. horizon·state·DP 한도는 결과에 남긴다.

**실제 함수·모델:** [pn_language_alignment.bounded_petri_net_anti_alignment](../../../src/pix/case_centric/pn_language_alignment.py), [pn_language_alignment.bounded_petri_net_multi_alignment](../../../src/pix/case_centric/pn_language_alignment.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_pn_language_alignment.py](../../../tests/case_centric/test_pn_language_alignment.py)

</details>

## CC-COMPLEXITY

**Arc-degree, Cardoso and cyclomatic simplicity**

### PM-CONF-019

**업무 질문:** 모델 복잡성을 서로 다른 구조 지표로 비교할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.simplicity_petri_net`

**참조 선택지:** `SIMPLICITY_ARC_DEGREE`, `EXTENDED_CARDOSO`, `EXTENDED_CYCLOMATIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Petri net과 지표 선택, 상태공간 기반 지표에 필요한 초기 marking.

**검토 대상 결과:** Arc-degree·extended Cardoso·extended cyclomatic 중 선택한 복잡성 지표.

**PIX 계산 정의:**

- Arc-degree simplicity, extended Cardoso and complete reachability-based cyclomatic.

**남은 차이·검증 범위:**

- State/token caps withhold full cyclomatic; formula conventions and every upstream model class are not equivalent by default.

**실제 함수·모델:** [model_analysis.model_complexity](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

## CC-QUALITY-REPORT

**Explicit multi-metric report composition**

### PM-CONF-025

**업무 질문:** 여러 품질 지표를 한 번에 재현 가능한 보고서로 묶을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.evaluation.algorithm.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·accepting Petri net과 지표별 평가·가중치 설정.

**검토 대상 결과:** Fitness·precision·generalization·simplicity 및 명시한 조합 점수를 묶은 평가 결과.

**PIX 계산 정의:**

- 모든 log 지표에 같은 TraceSet을 전달하며 fitness/token-or-alignment, precision, generalization, simplicity의 개별 결과와 명시 nonnegative weight를 결합한다. require_all 또는 renormalize_defined 정책, whole_source 모집단, 별도 fitness/precision F-score.

**남은 차이·검증 범위:**

- 각 지표의 PIX profile과 unknown coverage를 그대로 보존한다. 가중치는 사용자의 선호이며 보편적인 모델 품질 척도·upstream weight/missing 처리 동등성을 주장하지 않는다.

**실제 함수·모델:** [evaluation.evaluate_model](../../../src/pix/case_centric/evaluation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/test_evaluation.py](../../../tests/test_evaluation.py)

</details>

## CC-MODELS

**Classical model representations and executable semantics**

### PM-MODEL-001

**업무 질문:** Weighted Petri net의 marking에서 가능한 발화와 종료를 판정할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.petri_net.obj.PetriNet`, `pm4py.objects.petri_net.obj.Marking`, `pm4py.objects.petri_net.semantics.is_enabled`, `pm4py.objects.petri_net.semantics.execute` 외 4개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Weighted P/T net·현재 marking과 선택한 전이 또는 종료 marking.

**검토 대상 결과:** Enabled 전이 집합·발화 뒤 marking·종료 여부.

**PIX 계산 정의:**

- Immutable ordinary weighted P/T PetriNet and exact Marking; enabled firing and exact-final semantics
- ProcessTree activity/tau/sequence/xor/parallel/loop
- POWLNode activity/tau/xor/loop/strict partial order, SplitBPMN node/flow graph with validated supported gateways
- HeuristicsNet explicit dependency and binding model; TransitionSystem and prefix-tree output using state/edge structures
- IntegerRegion, SeparationTarget and RegionDiscovery are region-synthesis witness contracts; models_extended.py is not a general extended-model implementation
- NEW source: DataPetriNet wraps an ordinary accepting net with typed finite-numeric <=/> guards; DNF clauses within a decision, conjunction across affected decisions, missing/untrained inputs unknown. fire_data_transition requires both token enabling and guard true, then performs ordinary firing.
- Typed pix.model persistence now registers CC PetriNet, ProcessTree, HeuristicsNet, FootprintModel, TransitionSystem, DeclareModel, LogSkeleton, TemporalProfile, POWLNode, SplitBPMN and DataPetriNet with explicit semantic profiles, plus separate OC model types. This does not turn every registered model into an ordinary executable net.

**남은 차이·검증 범위:**

- implemented_narrow: ordinary weighted P/T; weak_execute API parity not asserted
- Reset/inhibitor semantics; broader guarded-data expression/update semantics; standalone stochastic P/T net contract; GeneticMatrix; full BPMN event/gateway semantics and model capability routing. Typed bare artifact registration and direct source tests exist; final aggregate execution evidence is recorded separately. CC conformance and model_analysis wrappers still explicitly require ordinary PetriNet, so registration is not universal conformance compatibility.

**실제 함수·모델:** [model_semantics.enabled_transitions](../../../src/pix/compute/model_semantics.py), [model_semantics.fire](../../../src/pix/compute/model_semantics.py), [model_semantics.is_enabled](../../../src/pix/compute/model_semantics.py), [model_semantics.is_final](../../../src/pix/compute/model_semantics.py).

<details>
<summary>관련 테스트 9개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)
- [tests/case_centric/test_heuristics.py](../../../tests/case_centric/test_heuristics.py)
- [tests/case_centric/test_models_extended.py](../../../tests/case_centric/test_models_extended.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_split_miner.py](../../../tests/case_centric/test_split_miner.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)
- [tests/compute/test_model_semantics.py](../../../tests/compute/test_model_semantics.py)
- [tests/test_decision_mining.py](../../../tests/test_decision_mining.py)
- [tests/test_extended_model_artifacts.py](../../../tests/test_extended_model_artifacts.py)

</details>

### PM-MODEL-002

**업무 질문:** Reset·inhibitor arc와 data guard를 가진 net을 해석할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.petri_net.obj.ResetNet`, `pm4py.objects.petri_net.obj.InhibitorNet`, `pm4py.objects.petri_net.obj.ResetInhibitorNet`, `pm4py.objects.petri_net.inhibitor_reset.semantics.execute` 외 3개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Reset/inhibitor/data net·marking·event data와 발화 또는 타입 변환 요청.

**검토 대상 결과:** 해당 arc/guard 의미의 enabled·발화 상태 또는 명시한 타입으로 변환한 모델.

**PIX 계산 정의:**

- Immutable ordinary weighted P/T PetriNet and exact Marking; enabled firing and exact-final semantics
- ProcessTree activity/tau/sequence/xor/parallel/loop
- POWLNode activity/tau/xor/loop/strict partial order, SplitBPMN node/flow graph with validated supported gateways
- HeuristicsNet explicit dependency and binding model; TransitionSystem and prefix-tree output using state/edge structures
- IntegerRegion, SeparationTarget and RegionDiscovery are region-synthesis witness contracts; models_extended.py is not a general extended-model implementation
- NEW source: DataPetriNet wraps an ordinary accepting net with typed finite-numeric <=/> guards; DNF clauses within a decision, conjunction across affected decisions, missing/untrained inputs unknown. fire_data_transition requires both token enabling and guard true, then performs ordinary firing.
- Typed pix.model persistence now registers CC PetriNet, ProcessTree, HeuristicsNet, FootprintModel, TransitionSystem, DeclareModel, LogSkeleton, TemporalProfile, POWLNode, SplitBPMN and DataPetriNet with explicit semantic profiles, plus separate OC model types. This does not turn every registered model into an ordinary executable net.

**남은 차이·검증 범위:**

- partial_native_profile: DataPetriNet typed finite-numeric guard evaluation and pure guarded firing source plus direct tests are present; reset/inhibitor semantics and arbitrary expression/state-update guards remain absent; final aggregate execution evidence is recorded separately
- Reset/inhibitor semantics; broader guarded-data expression/update semantics; standalone stochastic P/T net contract; GeneticMatrix; full BPMN event/gateway semantics and model capability routing. Typed bare artifact registration and direct source tests exist; final aggregate execution evidence is recorded separately. CC conformance and model_analysis wrappers still explicitly require ordinary PetriNet, so registration is not universal conformance compatibility.

**실제 함수·모델:** [decision_mining.data_petri_net_digest](../../../src/pix/case_centric/decision_mining.py), [decision_mining.evaluate_data_guards](../../../src/pix/case_centric/decision_mining.py), [decision_mining.fire_data_transition](../../../src/pix/case_centric/decision_mining.py).

<details>
<summary>관련 테스트 9개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)
- [tests/case_centric/test_heuristics.py](../../../tests/case_centric/test_heuristics.py)
- [tests/case_centric/test_models_extended.py](../../../tests/case_centric/test_models_extended.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_split_miner.py](../../../tests/case_centric/test_split_miner.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)
- [tests/compute/test_model_semantics.py](../../../tests/compute/test_model_semantics.py)
- [tests/test_decision_mining.py](../../../tests/test_decision_mining.py)
- [tests/test_extended_model_artifacts.py](../../../tests/test_extended_model_artifacts.py)

</details>

### PM-MODEL-003

**업무 질문:** 확률 전이와 분포를 가진 Petri net을 표현할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.petri_net.stochastic.obj.StochasticPetriNet`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Place·arc·확률 전이 속성과 사용할 분포/가중치 정의.

**검토 대상 결과:** 확률적 실행 정보를 담아 계산에 전달할 stochastic Petri net 모델.

**PIX 계산 정의:**

- Immutable ordinary weighted P/T PetriNet and exact Marking; enabled firing and exact-final semantics
- ProcessTree activity/tau/sequence/xor/parallel/loop
- POWLNode activity/tau/xor/loop/strict partial order, SplitBPMN node/flow graph with validated supported gateways
- HeuristicsNet explicit dependency and binding model; TransitionSystem and prefix-tree output using state/edge structures
- IntegerRegion, SeparationTarget and RegionDiscovery are region-synthesis witness contracts; models_extended.py is not a general extended-model implementation
- NEW source: DataPetriNet wraps an ordinary accepting net with typed finite-numeric <=/> guards; DNF clauses within a decision, conjunction across affected decisions, missing/untrained inputs unknown. fire_data_transition requires both token enabling and guard true, then performs ordinary firing.
- Typed pix.model persistence now registers CC PetriNet, ProcessTree, HeuristicsNet, FootprintModel, TransitionSystem, DeclareModel, LogSkeleton, TemporalProfile, POWLNode, SplitBPMN and DataPetriNet with explicit semantic profiles, plus separate OC model types. This does not turn every registered model into an ordinary executable net.

**남은 차이·검증 범위:**

- partial_support: simulation parameters supply transition weights and duration distributions, but no standalone persisted StochasticPetriNet contract
- Reset/inhibitor semantics; broader guarded-data expression/update semantics; standalone stochastic P/T net contract; GeneticMatrix; full BPMN event/gateway semantics and model capability routing. Typed bare artifact registration and direct source tests exist; final aggregate execution evidence is recorded separately. CC conformance and model_analysis wrappers still explicitly require ordinary PetriNet, so registration is not universal conformance compatibility.

**실제 함수·모델:** [simulation.playout_petri_net](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 9개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)
- [tests/case_centric/test_heuristics.py](../../../tests/case_centric/test_heuristics.py)
- [tests/case_centric/test_models_extended.py](../../../tests/case_centric/test_models_extended.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_split_miner.py](../../../tests/case_centric/test_split_miner.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)
- [tests/compute/test_model_semantics.py](../../../tests/compute/test_model_semantics.py)
- [tests/test_decision_mining.py](../../../tests/test_decision_mining.py)
- [tests/test_extended_model_artifacts.py](../../../tests/test_extended_model_artifacts.py)

</details>

### PM-MODEL-004

**업무 질문:** Tree·BPMN·POWL·Heuristics net·TS·trie 모델을 식별하고 읽을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.process_tree.obj.ProcessTree`, `pm4py.objects.bpmn.obj.BPMN`, `pm4py.objects.powl.obj.POWL`, `pm4py.objects.heuristics_net.obj.HeuristicsNet` 외 3개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 각 모델의 노드·관계·연산자·경계 및 모델별 필수 속성.

**검토 대상 결과:** 종류별 의미를 유지한 tree/BPMN/POWL/Heuristics net/TS/trie/GeneticMatrix 표현.

**PIX 계산 정의:**

- Immutable ordinary weighted P/T PetriNet and exact Marking; enabled firing and exact-final semantics
- ProcessTree activity/tau/sequence/xor/parallel/loop
- POWLNode activity/tau/xor/loop/strict partial order, SplitBPMN node/flow graph with validated supported gateways
- HeuristicsNet explicit dependency and binding model; TransitionSystem and prefix-tree output using state/edge structures
- IntegerRegion, SeparationTarget and RegionDiscovery are region-synthesis witness contracts; models_extended.py is not a general extended-model implementation
- NEW source: DataPetriNet wraps an ordinary accepting net with typed finite-numeric <=/> guards; DNF clauses within a decision, conjunction across affected decisions, missing/untrained inputs unknown. fire_data_transition requires both token enabling and guard true, then performs ordinary firing.
- Typed pix.model persistence now registers CC PetriNet, ProcessTree, HeuristicsNet, FootprintModel, TransitionSystem, DeclareModel, LogSkeleton, TemporalProfile, POWLNode, SplitBPMN and DataPetriNet with explicit semantic profiles, plus separate OC model types. This does not turn every registered model into an ordinary executable net.

**남은 차이·검증 범위:**

- partial_native_profile: tree/POWL/limited BPMN/heuristics/footprints/state/prefix representations exist and typed bare model persistence now registers the actual supported models; GeneticMatrix and full BPMN capabilities remain absent
- Reset/inhibitor semantics; broader guarded-data expression/update semantics; standalone stochastic P/T net contract; GeneticMatrix; full BPMN event/gateway semantics and model capability routing. Typed bare artifact registration and direct source tests exist; final aggregate execution evidence is recorded separately. CC conformance and model_analysis wrappers still explicitly require ordinary PetriNet, so registration is not universal conformance compatibility.

**실제 함수·모델:** [discovery.TransitionSystem](../../../src/pix/case_centric/discovery.py), [heuristics.HeuristicsNet](../../../src/pix/case_centric/heuristics.py), [powl.POWLNode](../../../src/pix/case_centric/powl.py), [split_miner.SplitBPMN](../../../src/pix/case_centric/split_miner.py), [discovery.ProcessTree](../../../src/pix/contracts/discovery.py).

<details>
<summary>관련 테스트 9개 파일</summary>

- [tests/case_centric/test_discovery.py](../../../tests/case_centric/test_discovery.py)
- [tests/case_centric/test_heuristics.py](../../../tests/case_centric/test_heuristics.py)
- [tests/case_centric/test_models_extended.py](../../../tests/case_centric/test_models_extended.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_split_miner.py](../../../tests/case_centric/test_split_miner.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)
- [tests/compute/test_model_semantics.py](../../../tests/compute/test_model_semantics.py)
- [tests/test_decision_mining.py](../../../tests/test_decision_mining.py)
- [tests/test_extended_model_artifacts.py](../../../tests/test_extended_model_artifacts.py)

</details>

## CC-CONVERT

**Direction-specific model conversion**

### PM-MODEL-005

**업무 질문:** Process tree를 실행 가능한 Petri net으로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_petri_net`

**참조 선택지:** `TO_PETRI_NET`, `TO_PETRI_NET_TRANSITION_BORDERED`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Process tree와 ordinary 또는 transition-bordered 변환 선택.

**검토 대상 결과:** Tree 실행을 표현하는 Petri net 및 초기/최종 marking.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- partial: ordinary tree conversion exists; transition-bordered variant absent
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [discovery.process_tree_to_petri_net](../../../src/pix/compute/discovery.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-006

**업무 질문:** Process tree를 BPMN 또는 POWL로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_bpmn`, `pm4py.convert.convert_to_powl`

**참조 선택지:** `TO_BPMN`, `TO_POWL`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Process tree와 BPMN 또는 POWL 목표 모델 종류.

**검토 대상 결과:** Tree 연산을 해당 gateway 또는 부분순서 구조로 표현한 목표 모델.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- implemented_native_subset: tree_to_bpmn and tree_to_powl cover supported PIX tree operators under bounds; BPMN output is the limited XOR/AND control-flow contract
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [model_conversion.tree_to_bpmn](../../../src/pix/case_centric/model_conversion.py), [model_conversion.tree_to_powl](../../../src/pix/case_centric/model_conversion.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-007

**업무 질문:** BPMN을 Petri net으로 변환하여 계산할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_petri_net`

**참조 선택지:** `TO_PETRI_NET`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 지원하는 task·event·gateway·flow를 포함한 BPMN 모델.

**검토 대상 결과:** BPMN 실행 의미를 표현하는 Petri net과 초기/최종 marking.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- partial_native_profile: bpmn_to_petri_net covers SplitBPMN task/plain-event/XOR/AND subset, not arbitrary BPMN
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [bpmn_conversion.bpmn_to_petri_net](../../../src/pix/case_centric/bpmn_conversion.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-008

**업무 질문:** Workflow net을 process tree 또는 BPMN으로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_process_tree`, `pm4py.convert.convert_to_bpmn`

**참조 선택지:** `TO_PROCESS_TREE`, `TO_BPMN`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Workflow Petri net·초기/최종 marking과 tree/BPMN 목표 선택.

**검토 대상 결과:** 변환 가능한 구조의 process tree 또는 BPMN, 불가능할 때의 실패 정보.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- partial_native_profile: supported unit-arc WF net to language-certified tree, then tree_to_bpmn; irreducible/weighted/general WF conversions remain gaps
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [model_conversion.tree_to_bpmn](../../../src/pix/case_centric/model_conversion.py), [wfnet_conversion.wfnet_to_process_tree](../../../src/pix/case_centric/wfnet_conversion.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-009

**업무 질문:** Petri net 또는 BPMN을 POWL로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_powl`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Workflow Petri net 또는 BPMN과 변환에 필요한 경계 정보.

**검토 대상 결과:** 분해 가능한 구조를 POWL로 표현한 모델 또는 변환 실패 정보.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- partial_composed_path: Petri net to certified WF tree to POWL, and BPMN to Petri net to certified WF tree to POWL; not arbitrary graph PN/BPMN-to-POWL conversion
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [bpmn_conversion.bpmn_to_petri_net](../../../src/pix/case_centric/bpmn_conversion.py), [model_conversion.tree_to_powl](../../../src/pix/case_centric/model_conversion.py), [wfnet_conversion.wfnet_to_process_tree](../../../src/pix/case_centric/wfnet_conversion.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-010

**업무 질문:** POWL을 net 또는 tree로 바꾸면 어떤 행동이 보존되는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_petri_net`, `pm4py.convert.convert_to_process_tree`

**참조 선택지:** `TO_PETRI_NET`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** POWL 모델과 Petri net 또는 process tree 목표 선택.

**검토 대상 결과:** 목표 모델과 net인 경우 초기/최종 marking, 해당 변환의 의미 보존 범위.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- partial: POWL to Petri net exists; POWL to process tree absent
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [powl.powl_to_petri_net](../../../src/pix/case_centric/powl.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-011

**업무 질문:** Heuristics net·GeneticMatrix·trie를 Petri net으로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.conversion.heuristics_net.converter.apply`, `pm4py.objects.conversion.genetic_matrix.converter.apply`, `pm4py.objects.conversion.trie.converter.apply`

**참조 선택지:** `TO_PETRI_NET`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Heuristics net·GeneticMatrix 또는 종료 정보가 있는 trie.

**검토 대상 결과:** 원본 모델의 결합·경계 의미를 표현한 Petri net과 초기/최종 marking.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- partial: heuristics binding converter source exists; GeneticMatrix/trie conversion absent
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [heuristics_conversion.heuristics_to_petri_net](../../../src/pix/case_centric/heuristics_conversion.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

### PM-MODEL-012

**업무 질문:** DFG를 서로 다른 구조의 Petri net으로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.conversion.dfg.converter.apply`

**참조 선택지:** `VERSION_TO_PETRI_NET_ACTIVITY_DEFINES_PLACE`, `VERSION_TO_PETRI_NET_INVISIBLES_NO_DUPLICATES`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** DFG·시작/종료 활동과 activity-place 또는 invisible 구성 선택.

**검토 대상 결과:** 선택한 구성 규칙의 Petri net과 초기/최종 marking.

**PIX 계산 정의:**

- Block tree to ordinary unit-arc workflow net with explicit source/sink and repeated-label occurrence identity
- POWL to accepting Petri net, preserving partial-order interleaving, xor and loop semantics under declared limits
- Heuristics bindings to obligation-token Petri net: one place per selected dependency, AND-set input/output bindings, exclusive boundary alternatives and exact sink-only final marking
- Tree to POWL: sequence total child order, parallel empty order, xor/loop preserved; tree to existing SplitBPMN XOR/AND task/plain-event profile with tau bypasses and explicit limits.
- SplitBPMN to weighted-P/T contract using unit sequence-flow places: XOR chooses/merges one, AND produces/consumes all; exact final marking and node/flow witnesses; unsupported BPMN elements are rejected.
- Unit-arc WF-net structural sequence/XOR/isolated fork-join/enclosed do-redo reductions; candidate tree released only after complete finite-state accepted-language equivalence certificate. Irreducible/weighted structures unavailable, capped verification partial without a tree.
- DFG activity_defines_place and invisibles_no_duplicates are distinct constructions of observed-boundary-constrained DFG walk language, with epsilon only when observed; frequencies do not become weights or probabilities.

**남은 차이·검증 범위:**

- implemented_native_profiles: both activity_defines_place and invisibles_no_duplicates; boundary-constrained walk-language contracts and direct tests, not upstream output parity
- Tree-to-Petri transition-bordered variant; broad BPMN inclusive/event/subprocess/data/message/time semantics; arbitrary irreducible or weighted WF/PN to tree/BPMN/POWL; POWL-to-tree; GeneticMatrix/trie-to-Petri conversions. Supported composed conversion pipelines preserve accepted language within their explicit contracts and limits, not every reference representation or option. Heuristics converter remains the explicit obligation-token profile.

**실제 함수·모델:** [dfg_conversion.dfg_to_petri_net](../../../src/pix/case_centric/dfg_conversion.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/case_centric/test_bpmn_conversion.py](../../../tests/case_centric/test_bpmn_conversion.py)
- [tests/case_centric/test_dfg_conversion.py](../../../tests/case_centric/test_dfg_conversion.py)
- [tests/case_centric/test_heuristics_conversion.py](../../../tests/case_centric/test_heuristics_conversion.py)
- [tests/case_centric/test_model_conversion.py](../../../tests/case_centric/test_model_conversion.py)
- [tests/case_centric/test_powl.py](../../../tests/case_centric/test_powl.py)
- [tests/case_centric/test_wfnet_conversion.py](../../../tests/case_centric/test_wfnet_conversion.py)
- [tests/compute/test_discovery.py](../../../tests/compute/test_discovery.py)

</details>

## CC-REACHABILITY

**Reachability, WF-net and soundness properties**

### PM-MODEL-013

**업무 질문:** 현재 marking에서 도달 가능한 전체 상태와 전이는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_to_reachability_graph`, `pm4py.objects.petri_net.utils.reachability_graph.construct_reachability_graph`, `pm4py.objects.petri_net.utils.reachability_graph.marking_flow_petri`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Petri net·초기 marking과 상태/시간 탐색 한도.

**검토 대상 결과:** 도달 marking을 상태로 하는 graph·발화 edge와 탐색 완전성 정보.

**PIX 계산 정의:**

- Breadth-first exact weighted marking graph; state/token caps, actual excluded-edge witnesses, enabled IDs and exact final-state index
- Workflow-net shape and accepting marking checks separately; unique source/sink and all-node source-to-sink coverage
- Classical one-token workflow soundness: option to complete, proper completion, no dead transitions. Complete finite graph proves; capped search stays unknown unless an actual reachable deadlock/improper completion refutes
- Exact primitive-integer rational nullspace basis for P/T invariants, not positive invariant cone or integer lattice

**남은 차이·검증 범위:**

- implemented_narrow: finite complete reachability or explicit partial frontier
- General coverability/unboundedness certificates, S-components, full WOFLAN non-live/unbounded-sequence diagnostics and arbitrary-net liveness. Exhausting a resource cap is not proof of unboundedness or unsoundness.

**실제 함수·모델:** [model_analysis.reachability](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_model_algebra.py](../../../tests/case_centric/test_model_algebra.py)
- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

### PM-MODEL-014

**업무 질문:** 모델이 workflow-net 구조 조건을 만족하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.check_is_workflow_net`

**참조 선택지:** `PETRI_NET`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Place·transition·arc로 구성한 Petri net.

**검토 대상 결과:** Unique source/sink와 경로 포함 조건에 따른 workflow-net 판정.

**PIX 계산 정의:**

- Breadth-first exact weighted marking graph; state/token caps, actual excluded-edge witnesses, enabled IDs and exact final-state index
- Workflow-net shape and accepting marking checks separately; unique source/sink and all-node source-to-sink coverage
- Classical one-token workflow soundness: option to complete, proper completion, no dead transitions. Complete finite graph proves; capped search stays unknown unless an actual reachable deadlock/improper completion refutes
- Exact primitive-integer rational nullspace basis for P/T invariants, not positive invariant cone or integer lattice

**남은 차이·검증 범위:**

- implemented_narrow: graph shape and accepting-marking definitions explicit
- General coverability/unboundedness certificates, S-components, full WOFLAN non-live/unbounded-sequence diagnostics and arbitrary-net liveness. Exhausting a resource cap is not proof of unboundedness or unsoundness.

**실제 함수·모델:** [model_analysis.check_workflow_net](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_model_algebra.py](../../../tests/case_centric/test_model_algebra.py)
- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

### PM-MODEL-015

**업무 질문:** Workflow net은 종료 가능성·dead transition·boundedness 등 soundness를 만족하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.check_soundness`, `pm4py.analysis.check_is_sound`, `pm4py.algo.analysis.woflan.algorithm.compute_non_live_sequences`, `pm4py.algo.analysis.woflan.algorithm.compute_unbounded_sequences` 외 14개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Workflow 후보 Petri net·초기/최종 marking과 분석 한도.

**검토 대상 결과:** Soundness 판정 및 boundedness·liveness·dead transition 등의 진단/반례.

**PIX 계산 정의:**

- Breadth-first exact weighted marking graph; state/token caps, actual excluded-edge witnesses, enabled IDs and exact final-state index
- Workflow-net shape and accepting marking checks separately; unique source/sink and all-node source-to-sink coverage
- Classical one-token workflow soundness: option to complete, proper completion, no dead transitions. Complete finite graph proves; capped search stays unknown unless an actual reachable deadlock/improper completion refutes
- Exact primitive-integer rational nullspace basis for P/T invariants, not positive invariant cone or integer lattice

**남은 차이·검증 범위:**

- partial: finite-state workflow soundness and rational invariants; complete WOFLAN machinery absent
- General coverability/unboundedness certificates, S-components, full WOFLAN non-live/unbounded-sequence diagnostics and arbitrary-net liveness. Exhausting a resource cap is not proof of unboundedness or unsoundness.

**실제 함수·모델:** [model_analysis.check_soundness](../../../src/pix/case_centric/model_analysis.py), [model_analysis.model_invariants](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_model_algebra.py](../../../tests/case_centric/test_model_algebra.py)
- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

## CC-OPTIMIZATION

**Marking equation and extended lower-bound problems**

### PM-MODEL-016

**업무 질문:** Marking equation으로 도달 비용 하한을 계산할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.solve_marking_equation`, `pm4py.algo.analysis.marking_equation.algorithm.build`, `pm4py.algo.analysis.marking_equation.algorithm.get_h_value`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Petri net·초기/최종 marking·전이 비용과 LP/ILP 설정.

**검토 대상 결과:** Marking equation 최적 목적값인 비용 하한과 solver 해/실패 상태.

**PIX 계산 정의:**

- Exact output-minus-input integer incidence and rational nullspace
- Current public marking_equation_bound invokes native exact nonnegative rational LP by finite column-basis enumeration; optional initial/target markings and exact nonnegative costs are in request identity
- Limited enumeration reports unknown, no certified objective; incumbent is an LP upper bound, not reachable-path evidence
- New internal _equation_solver.solve_lp source implements two-phase rational simplex with exact primal/dual or Farkas certificate validation; it is not currently called by model_analysis.marking_equation_bound
- NEW concurrent marking_equation.py: integer_marking_equation uses bounded total-firing enumeration and unrestricted rational lower bounds; extended_marking_equation constructs k+1 segments plus split-occurrence choices with weighted Pre consumption and explicit equations. Neither feasible integer counts nor segmented constraints prove execution.

**남은 차이·검증 범위:**

- partial: tested rational LP bound; new bounded-integer implementation source, runtime validation not inspected
- Current marking_equation.py source and tests/test_marking_equation.py plus test_equation_solver.py are present; final aggregate execution evidence is recorded separately. Bounded integer enumeration is not unrestricted ILP optimality. Extended equation uses occurrence-specific split transitions and weighted Pre consumption, differing from pinned upstream behavior. Scalability, complete variant coverage and numerical parity remain unestablished.

**실제 함수·모델:** [marking_equation.integer_marking_equation](../../../src/pix/case_centric/marking_equation.py), [model_analysis.marking_equation_bound](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/case_centric/test_equation_solver.py](../../../tests/case_centric/test_equation_solver.py)
- [tests/case_centric/test_model_algebra.py](../../../tests/case_centric/test_model_algebra.py)
- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)
- [tests/test_marking_equation.py](../../../tests/test_marking_equation.py)

</details>

### PM-MODEL-017

**업무 질문:** Split point를 가진 extended marking equation 하한은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.solve_extended_marking_equation`, `pm4py.algo.analysis.extended_marking_equation.algorithm.build`, `pm4py.algo.analysis.extended_marking_equation.algorithm.get_h_value`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace·synchronous-product net·초기/최종 marking과 split point·비용.

**검토 대상 결과:** 중간 제약을 반영한 extended marking equation 비용 하한과 해 상태.

**PIX 계산 정의:**

- Exact output-minus-input integer incidence and rational nullspace
- Current public marking_equation_bound invokes native exact nonnegative rational LP by finite column-basis enumeration; optional initial/target markings and exact nonnegative costs are in request identity
- Limited enumeration reports unknown, no certified objective; incumbent is an LP upper bound, not reachable-path evidence
- New internal _equation_solver.solve_lp source implements two-phase rational simplex with exact primal/dual or Farkas certificate validation; it is not currently called by model_analysis.marking_equation_bound
- NEW concurrent marking_equation.py: integer_marking_equation uses bounded total-firing enumeration and unrestricted rational lower bounds; extended_marking_equation constructs k+1 segments plus split-occurrence choices with weighted Pre consumption and explicit equations. Neither feasible integer counts nor segmented constraints prove execution.

**남은 차이·검증 범위:**

- new_source_unverified: occurrence-based split-point extended equation with weighted consumption, independent runtime evidence not inspected
- Current marking_equation.py source and tests/test_marking_equation.py plus test_equation_solver.py are present; final aggregate execution evidence is recorded separately. Bounded integer enumeration is not unrestricted ILP optimality. Extended equation uses occurrence-specific split transitions and weighted Pre consumption, differing from pinned upstream behavior. Scalability, complete variant coverage and numerical parity remain unestablished.

**실제 함수·모델:** [marking_equation.extended_marking_equation](../../../src/pix/case_centric/marking_equation.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/case_centric/test_equation_solver.py](../../../tests/case_centric/test_equation_solver.py)
- [tests/case_centric/test_model_algebra.py](../../../tests/case_centric/test_model_algebra.py)
- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)
- [tests/test_marking_equation.py](../../../tests/test_marking_equation.py)

</details>

## CC-SYNCHRONOUS-PRODUCT

**Cost-aware log-model synchronous product**

### PM-MODEL-018

**업무 질문:** Trace와 모델의 synchronous product를 구성할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.construct_synchronous_product_net`, `pm4py.objects.petri_net.utils.synchronous_product.construct`, `pm4py.objects.petri_net.utils.synchronous_product.construct_cost_aware`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace·Petri net·초기/최종 marking과 선택적인 이동별 비용.

**검토 대상 결과:** Log/model/synchronous 전이를 구분한 product net·초기/최종 marking 및 비용 대응.

**PIX 계산 정의:**

- Existing internal alignment moves and state-equation relaxation
- NEW concurrent public synchronous_product source constructs weighted model and trace places, log/model/silent/synchronous transitions, per-move exact rational costs and trace-index/model-transition provenance

**남은 차이·검증 범위:**

- new_source_unverified: explicit product contract and cost/source mapping appeared during audit; runtime proof/test result not inspected
- Current explicit product source and direct marking-equation/product test file are present; no passing run inspected. Direct product correctness, source mapping/cost validation, persistence and publication integration remain verification work. Earlier alignment tests alone do not certify this public product constructor.

**실제 함수·모델:** [marking_equation.synchronous_product](../../../src/pix/case_centric/marking_equation.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_alignment_search.py](../../../tests/case_centric/test_alignment_search.py)
- [tests/test_marking_equation.py](../../../tests/test_marking_equation.py)

</details>

## CC-DECOMPOSITION

**Maximal decomposition and recomposition**

### PM-MODEL-019

**업무 질문:** 모델을 최대 구성요소로 분해하고 다시 조합할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.maximal_decomposition`, `pm4py.objects.petri_net.utils.decomposition.decompose`, `pm4py.objects.petri_net.utils.decomposition.merge_comp`, `pm4py.objects.petri_net.utils.decomposition.merge_sublist_nets`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Accepting Petri net 또는 병합할 부분 net과 marking.

**검토 대상 결과:** 최대 분해 구성요소 목록 또는 재조합한 net·marking.

**PIX 계산 정의:**

- Weak connected components of weighted incidence graph, including isolated places/transitions, exact marking projections; independent shuffle-product composition
- Separate decomposed alignment allocates each shared-label event to one disjoint component and recomposes executable alignment evidence under complete enumeration

**남은 차이·검증 범위:**

- partial_overlap: weak disjoint components are not reference maximal decomposition with shared border transitions
- Maximal decomposition, shared invisible/equal-label border semantics, merge_comp and merge_sublist_nets equivalents; RPST/SESE decomposition if chosen for related conversion work. Current connected-net decomposition does not deliver those properties.

**실제 함수·모델:** [model_analysis.decompose_model](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_decomposed_alignment.py](../../../tests/case_centric/test_decomposed_alignment.py)
- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

## CC-REDUCTION

**Meaning-preserving net and trace-specific tree reduction**

### PM-MODEL-020

**업무 질문:** 불필요한 invisible 구조나 implicit place를 의미를 보존하며 제거할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.reduce_petri_net_invisibles`, `pm4py.analysis.reduce_petri_net_implicit_places`, `pm4py.objects.petri_net.utils.reduction.apply_simple_reduction`, `pm4py.objects.petri_net.utils.murata.apply_reduction` 외 1개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 지원하는 ordinary/reset/inhibitor net·marking과 reduction 규칙 선택.

**검토 대상 결과:** 선택한 보존 조건에서 축약한 net·marking 및 원본 구조 대응.

**PIX 계산 정의:**

- silent_identity
- duplicate_transition
- duplicate_place
- language.v1: associative flattening, neutral tau in sequence/parallel, duplicate XOR alternatives, explicit XOR tau removal only when another branch is nullable; binary loop distinctions preserved.
- nullable_disjoint.v1: for one specified trace, replace only nullable subtrees with disjoint activity alphabet by tau, then fold; root excluded unless opted in; minimum insertion/deletion cost preserved for zero synchronous/silent and finite nonnegative constant log/model costs.

**남은 차이·검증 범위:**

- partial: three proven local ordinary-net rules; full invisible/Murata/implicit-place/reset-inhibitor families absent
- General Murata/invisible/implicit-place and reset/inhibitor reduction families remain missing. Trace-relative reduction now exists with source/epsilon witnesses but does not support arbitrary alignment-cost profiles or full-language preservation.

**실제 함수·모델:** [model_analysis.reduce_model](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)
- [tests/case_centric/test_tree_reduction.py](../../../tests/case_centric/test_tree_reduction.py)

</details>

### PM-MODEL-024

**업무 질문:** 지정 trace 분석에 불필요한 선택적 tree 부분을 줄일 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.reduction.process_tree.variants.tree_tr_based.reduce`

**참조 선택지:** `TREE_TR_BASED`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Process tree·비교할 단일 trace와 활동 classifier.

**검토 대상 결과:** 해당 trace와 겹치지 않는 skippable 부분을 tau로 치환하고 접은 process tree.

**PIX 계산 정의:**

- silent_identity
- duplicate_transition
- duplicate_place
- language.v1: associative flattening, neutral tau in sequence/parallel, duplicate XOR alternatives, explicit XOR tau removal only when another branch is nullable; binary loop distinctions preserved.
- nullable_disjoint.v1: for one specified trace, replace only nullable subtrees with disjoint activity alphabet by tau, then fold; root excluded unless opted in; minimum insertion/deletion cost preserved for zero synchronous/silent and finite nonnegative constant log/model costs.

**남은 차이·검증 범위:**

- implemented_native_subset: full-language structural fold and fixed-trace nullable-disjoint reduction; fixed-trace edit-alignment guarantee only under declared cost assumptions
- General Murata/invisible/implicit-place and reset/inhibitor reduction families remain missing. Trace-relative reduction now exists with source/epsilon witnesses but does not support arbitrary alignment-cost profiles or full-language preservation.

**실제 함수·모델:** [tree_reduction.fold_process_tree](../../../src/pix/case_centric/tree_reduction.py), [tree_reduction.reduce_process_tree_for_trace](../../../src/pix/case_centric/tree_reduction.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)
- [tests/case_centric/test_tree_reduction.py](../../../tests/case_centric/test_tree_reduction.py)

</details>

## CC-MODEL-GRAPH

**Structural graph and activity relabeling**

### PM-MODEL-021

**업무 질문:** 모델을 graph로 전달하고 활동 label을 읽거나 바꿀 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_petri_net_to_networkx`, `pm4py.analysis.get_activity_labels`, `pm4py.analysis.replace_activity_labels`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Petri net 또는 지원 모델과 graph 투영/label 조회·치환 요청.

**검토 대상 결과:** Graph 표현·활동 label 목록 또는 label을 치환한 모델.

**PIX 계산 정의:**

- Immutable model graph view for PetriNet/OCPN or their ModelArtifact: distinct transition IDs despite duplicate labels, arc weight/direction, initial/final markings and declared provenance

**남은 차이·검증 범위:**

- partial: graph view exists; generic get_activity_labels/replace_activity_labels with model provenance absent
- Type-aware label reading/replacement and change provenance; projections for additional model types. NetworkX object API compatibility is a separate boundary, not required merely because a structural graph exists.

**실제 함수·모델:** [model_adapter.build_model_graph](../../../src/pix/viewer/model_adapter.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/viewer/test_model_graph.py](../../../tests/viewer/test_model_graph.py)

</details>

## CC-MODEL-SIMILARITY

**Behavioral/structural/embedding/label similarity**

### PM-MODEL-022

**업무 질문:** 두 모델이 행동·구조 관점에서 얼마나 비슷한가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.behavioral_similarity`, `pm4py.analysis.structural_similarity`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 비교 가능한 모델 두 개와 행동/구조 유사도 선택.

**검토 대상 결과:** Footprints 또는 tree 구조에 근거한 모델 간 유사도 점수.

**PIX 계산 정의:**

- language: accepted-language equivalence using complete finite marking graphs, epsilon closures, subset construction and BFS product; returns a distinguishing accepted word on inequivalence and unknown on caps
- label_set: exact rational Jaccard over distinct non-silent activity strings, empty/empty equals one
- identity_structure: exact rational Jaccard over node-ID-sensitive place/transition/weighted-arc/accepting-marking tokens

**남은 차이·검증 범위:**

- partial_overlap: native language equivalence and ID-sensitive structure differ from reference footprint and process-tree scores
- Reference footprint sequence/parallel behavioral scores, process-tree structural scores, model embedding similarity, string-semantic matching and label replacement mappings. Current set scores make no behavioral-equivalence claim.

**실제 함수·모델:** [model_analysis.compare_models](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

### PM-MODEL-023

**업무 질문:** 모델 embedding 또는 label 의미로 유사도와 label 매핑을 구할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.embeddings_similarity`, `pm4py.analysis.label_sets_similarity`, `pm4py.analysis.map_labels_from_second_model`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 모델 두 개·label 집합과 embedding/문자열 유사도·threshold 설정.

**검토 대상 결과:** Embedding/label 유사도 또는 대응 label로 변경한 모델과 매핑.

**PIX 계산 정의:**

- language: accepted-language equivalence using complete finite marking graphs, epsilon closures, subset construction and BFS product; returns a distinguishing accepted word on inequivalence and unknown on caps
- label_set: exact rational Jaccard over distinct non-silent activity strings, empty/empty equals one
- identity_structure: exact rational Jaccard over node-ID-sensitive place/transition/weighted-arc/accepting-marking tokens

**남은 차이·검증 범위:**

- partial_overlap: exact label-set Jaccard exists; embeddings, fuzzy label similarity and directional matching absent
- Reference footprint sequence/parallel behavioral scores, process-tree structural scores, model embedding similarity, string-semantic matching and label replacement mappings. Current set scores make no behavioral-equivalence claim.

**실제 함수·모델:** [model_analysis.compare_models](../../../src/pix/case_centric/model_analysis.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_model_analysis.py](../../../tests/case_centric/test_model_analysis.py)

</details>

## CC-STATISTICS

**Case/event attributes, variants, activity relations and duration distributions**

### PM-DATA-002

**업무 질문:** 이벤트·case에서 어떤 속성이 관측되고 값이 얼마나 나타나는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_event_attributes`, `pm4py.stats.get_trace_attributes`, `pm4py.stats.get_event_attribute_values`, `pm4py.stats.get_trace_attribute_values`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트·case 속성과 scope, 값 타입, per-case 중복 집계 정책.

**검토 대상 결과:** 속성 이름·값별 빈도·누락률과 집계 모집단.

**PIX 계산 정의:**

- typed event/case 속성 빈도·case membership·missing coverage; 중첩값은 typed JSON token으로 유지.

**남은 차이·검증 범위:**

- 모든 backend 정렬과 callback 동등성은 미검증. null/missing/type 차이를 합치지 않는다.

**실제 함수·모델:** [statistics.measure_attributes](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-003

**업무 질문:** 동일 활동열의 case들은 무엇이며 variant 빈도·coverage는 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_variants`, `pm4py.stats.get_variants_as_tuples`, `pm4py.stats.split_by_process_variant`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 정렬된 활동열, classifier와 선택 case 집합.

**검토 대상 결과:** 활동열 variant별 case ID·빈도·coverage 및 분할 로그.

**PIX 계산 정의:**

- 활동·시작/끝·rework·position·tuple variant·최소 self-distance와 witness를 source-order로 계산한다.

**남은 차이·검증 범위:**

- Case와 event의 분모를 분리한다. 임의 참조 정렬/backend 동등성을 주장하지 않는다.

**실제 함수·모델:** [statistics.measure_statistics](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-004

**업무 질문:** 각 variant의 반복 경로별 소요시간 분포는 어떠한가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_variants_paths_duration`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case variant와 각 event의 start/complete, 반복 경로 위치.

**검토 대상 결과:** Variant·path occurrence별 기간 표본과 집계.

**PIX 계산 정의:**

- variant occurrence position별 completion gap·서비스·case 시간 증거.

**남은 차이·검증 범위:**

- 전용 PRE/POST/PREPOST aggregate, next-start waiting, business calendar는 미구현이다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-005

**업무 질문:** 관측 로그 또는 모델의 trace 확률 언어는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_stochastic_language`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 관측 case log 또는 PN/tree/DFG 모델과 playout 설정.

**검토 대상 결과:** Trace별 확률과 근사·미관측·절단 질량 정보.

**PIX 계산 정의:**

- 관측 variant probability를 계산한다.

**남은 차이·검증 범위:**

- 임의 모델의 전체 stochastic language는 이 함수가 계산하지 않는다. Simulation의 유한/표본 언어는 별도 제한을 갖는다.

**실제 함수·모델:** [statistics.measure_statistics](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-006

**업무 질문:** 같은 활동이 다시 나타날 때 최소 몇 개 활동을 거치고 어떤 활동이 사이에 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_minimum_self_distances`, `pm4py.stats.get_minimum_self_distance_witnesses`, `pm4py.discovery.derive_minimum_self_distance`

**참조 선택지:** `LOG`, `PANDAS`, `POLARS`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 기록 순서가 있는 활동열과 activity key.

**검토 대상 결과:** 활동별 최소 재발 거리와 그 사이의 witness 활동 집합.

**PIX 계산 정의:**

- 활동·시작/끝·rework·position·tuple variant·최소 self-distance와 witness를 source-order로 계산한다.

**남은 차이·검증 범위:**

- Case와 event의 분모를 분리한다. 임의 참조 정렬/backend 동등성을 주장하지 않는다.

**실제 함수·모델:** [statistics.measure_statistics](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-007

**업무 질문:** Case의 평균 도착 간격과 종료 간격은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_case_arrival_average`, `pm4py.statistics.traces.generic.log.case_arrival.get_case_arrival_avg`, `pm4py.statistics.traces.generic.log.case_arrival.get_case_dispersion_avg`, `pm4py.analysis.insert_case_arrival_finish_rate`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 최초·최종 event 시각과 calendar 정책.

**검토 대상 결과:** Case 도착·종료 간격의 표본 수와 평균.

**PIX 계산 정의:**

- 명시 완료 시각·start attribute에서 arrival/finish gap, span, overlap, service, case 내 concurrency, 완전한 service-case의 busy union/case 수를 계산한다.

**남은 차이·검증 범위:**

- 결측 시각은 unknown. Business calendar·unfinished-case 추정·global cross-case service overlap은 별도다. Strict/inclusive endpoint와 cycle 분모는 명시한다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-008

**업무 질문:** 활동별로 재작업한 case 수와 반복 이벤트 수는 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_rework_cases_per_activity`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 활동열과 재작업 횟수 정의.

**검토 대상 결과:** 활동별 재작업 case 수·비율 또는 반복 occurrence 수.

**PIX 계산 정의:**

- 활동·시작/끝·rework·position·tuple variant·최소 self-distance와 witness를 source-order로 계산한다.

**남은 차이·검증 범위:**

- Case와 event의 분모를 분리한다. 임의 참조 정렬/backend 동등성을 주장하지 않는다.

**실제 함수·모델:** [statistics.measure_statistics](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-009

**업무 질문:** 동시에 진행되는 case 또는 실행 구간은 몇 개인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_case_overlap`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case span 또는 start/complete interval들과 경계 포함 정책.

**검토 대상 결과:** 각 구간의 overlap 수와 겹치는 구간 근거.

**PIX 계산 정의:**

- 명시 완료 시각·start attribute에서 arrival/finish gap, span, overlap, service, case 내 concurrency, 완전한 service-case의 busy union/case 수를 계산한다.

**남은 차이·검증 범위:**

- 결측 시각은 unknown. Business calendar·unfinished-case 추정·global cross-case service overlap은 별도다. Strict/inclusive endpoint와 cycle 분모는 명시한다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-010

**업무 질문:** 겹치는 구간을 고려한 cycle time은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_cycle_time`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 실행 구간과 case 수, cycle-time 정의.

**검토 대상 결과:** 구간 union 기반 cycle time과 계산 분자·분모.

**PIX 계산 정의:**

- 명시 완료 시각·start attribute에서 arrival/finish gap, span, overlap, service, case 내 concurrency, 완전한 service-case의 busy union/case 수를 계산한다.

**남은 차이·검증 범위:**

- 결측 시각은 unknown. Business calendar·unfinished-case 추정·global cross-case service overlap은 별도다. Strict/inclusive endpoint와 cycle 분모는 명시한다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-011

**업무 질문:** 실제 시작·완료가 기록된 활동의 service time은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_service_time`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동별 명시 start·complete와 aggregation/calendar 설정.

**검토 대상 결과:** Service time 표본·집계·미측정 coverage.

**PIX 계산 정의:**

- 명시 완료 시각·start attribute에서 arrival/finish gap, span, overlap, service, case 내 concurrency, 완전한 service-case의 busy union/case 수를 계산한다.

**남은 차이·검증 범위:**

- 결측 시각은 unknown. Business calendar·unfinished-case 추정·global cross-case service overlap은 별도다. Strict/inclusive endpoint와 cycle 분모는 명시한다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-012

**업무 질문:** Case 전체와 개별 case의 기간 분포는 어떠한가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_all_case_durations`, `pm4py.stats.get_case_duration`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 event 시각, 선택 case ID와 calendar.

**검토 대상 결과:** 전체·개별 case duration과 분포·미완료 표식.

**PIX 계산 정의:**

- 명시 완료 시각·start attribute에서 arrival/finish gap, span, overlap, service, case 내 concurrency, 완전한 service-case의 busy union/case 수를 계산한다.

**남은 차이·검증 범위:**

- 결측 시각은 unknown. Business calendar·unfinished-case 추정·global cross-case service overlap은 별도다. Strict/inclusive endpoint와 cycle 분모는 명시한다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-013

**업무 질문:** 자주 등장하는 부분 활동열은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_frequent_trace_segments`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 최소 지원도, subsequence 의미.

**검토 대상 결과:** 빈발 부분열과 case 지원도·매칭 근거.

**PIX 계산 정의:**

- Case별 한 번 세는 gapped subsequence 또는 contiguous segment support와 earliest witness.

**남은 차이·검증 범위:**

- 명시 max length·candidate budget 내 계산이며 무제한 탐색·wildcard 문자열 호환을 뜻하지 않는다.

**실제 함수·모델:** [statistics.discover_frequent_sequences](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-014

**업무 질문:** 활동이 case의 몇 번째 위치에서 발생하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_activity_position_summary`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 source-order 활동열.

**검토 대상 결과:** 활동별 0/1 기반 위치와 빈도 분포.

**PIX 계산 정의:**

- 활동·시작/끝·rework·position·tuple variant·최소 self-distance와 witness를 source-order로 계산한다.

**남은 차이·검증 범위:**

- Case와 event의 분모를 분리한다. 임의 참조 정렬/backend 동등성을 주장하지 않는다.

**실제 함수·모델:** [statistics.measure_statistics](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-015

**업무 질문:** 두 속성 축으로 나눈 process cube의 집계 결과는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.stats.get_process_cube`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case/event 표와 X/Y 속성, bin 경계, 집계 함수.

**검토 대상 결과:** 셀별 모집단·집계값을 가진 process cube.

**PIX 계산 정의:**

- 두 typed categorical dimension과 명시 missing cell의 count·case membership·finite numeric aggregate.

**남은 차이·검증 범위:**

- Numeric dimension binning 및 임의 aggregation callback은 미구현이다.

**실제 함수·모델:** [statistics.build_process_cube](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-016

**업무 질문:** 주어진 활동 전후에 얼마의 시간이 걸리는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.statistics.passed_time.log.algorithm.apply`, `pm4py.statistics.passed_time.pandas.algorithm.apply`, `pm4py.statistics.passed_time.polars.algorithm.apply`

**참조 선택지:** `PRE`, `POST`, `PREPOST`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 선택 활동과 인접 경로의 event 시각, PRE/POST/PREPOST.

**검토 대상 결과:** 활동 전후 경로별 시간과 가중 집계.

**PIX 계산 정의:**

- variant occurrence position별 completion gap·서비스·case 시간 증거.

**남은 차이·검증 범위:**

- 전용 PRE/POST/PREPOST aggregate, next-start waiting, business calendar는 미구현이다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-017

**업무 질문:** 활동 실행 구간의 겹침으로 본 concurrent 활동쌍은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.statistics.concurrent_activities.log.get.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 실행 interval과 strict overlap 정책.

**검토 대상 결과:** 동시 활동쌍별 겹침 빈도와 대상 interval.

**PIX 계산 정의:**

- 명시 완료 시각·start attribute에서 arrival/finish gap, span, overlap, service, case 내 concurrency, 완전한 service-case의 busy union/case 수를 계산한다.

**남은 차이·검증 범위:**

- 결측 시각은 unknown. Business calendar·unfinished-case 추정·global cross-case service overlap은 별도다. Strict/inclusive endpoint와 cycle 분모는 명시한다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-018

**업무 질문:** 활동쌍의 eventually-follows 빈도는 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_eventually_follows_graph`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 first/all occurrence 계산 정책.

**검토 대상 결과:** Eventually-follows 활동쌍 빈도와 occurrence 근거.

**PIX 계산 정의:**

- Source-position eventually follows와 explicit interval start-order/completion≤next-start의 별도 계산.

**남은 차이·검증 범위:**

- 동률 정책과 event 순서가 명시된다. 두 계산을 동일한 인과 관계로 해석하지 않는다.

**실제 함수·모델:** [statistics.discover_interval_eventually_follows](../../../src/pix/case_centric/statistics.py), [statistics.measure_statistics](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-019

**업무 질문:** 숫자 속성·기간의 연속 분포와 시간 단위별 빈도는 어떠한가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.statistics.attributes.common.get.get_kde_numeric_attribute`, `pm4py.statistics.attributes.common.get.get_kde_numeric_attribute_json`, `pm4py.statistics.attributes.log.get.get_events_distribution`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 수치/시각 속성 표본과 bin·bandwidth·샘플링 설정.

**검토 대상 결과:** 빈도 분포 또는 KDE 추정 좌표와 설정.

**PIX 계산 정의:**

- Caller grid/bandwidth의 Gaussian KDE, numeric summary와 fixed-offset calendar bins.

**남은 차이·검증 범위:**

- 자동 bandwidth, duration-KDE facade, IANA timezone/DST calendar가 남아 있다.

**실제 함수·모델:** [statistics.measure_event_distribution](../../../src/pix/case_centric/statistics.py), [statistics.measure_numeric_attribute](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-020

**업무 질문:** 여러 활동을 통과하는 시간 경로의 performance spectrum은 어떠한가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.performance_spectrum.algorithm.is_polars_lazyframe`

**참조 선택지:** `DATAFRAME`, `LOG`, `DATAFRAME_DISCONNECTED`, `LOG_DISCONNECTED`, `LAZYFRAME`, `LAZYFRAME_DISCONNECTED`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 지정 활동열과 event 시각, connected/disconnected 및 sample 한도.

**검토 대상 결과:** Performance-spectrum 시간 좌표들의 집합과 표본 범위.

**PIX 계산 정의:**

- projected-contiguous/source-contiguous/subsequence의 timestamp vector.

**남은 차이·검증 범위:**

- Disconnected maximal-fragment, reference sampling 및 암묵적 timestamp-sorted profile은 미구현이다.

**실제 함수·모델:** [statistics.discover_performance_spectrum](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-021

**업무 질문:** 관측 순서가 복잡하고 불규칙한 활동을 어떻게 찾는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.statistics.chaotic_activities.algorithm.apply`

**참조 선택지:** `NIEK_SIDOROVA`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 순서가 있는 log와 alpha 등 chaotic 판정 설정.

**검토 대상 결과:** 불규칙 활동 판정과 계산된 기준값.

**PIX 계산 정의:**

- 전후 neighborhood entropy와 activity 삭제 후 gain의 명시 수식.

**남은 차이·검증 범위:**

- 순서 불규칙성 통계이며 잘못된 활동의 인과적 판정이 아니다. Referenced score/backend 전범위 parity는 미검증.

**실제 함수·모델:** [statistics.discover_chaotic_activities](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

### PM-DATA-038

**업무 질문:** Case 전체의 service·sojourn·waiting을 집계하여 붙일 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.insert_case_service_waiting_time`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case의 start/complete interval과 합집합·calendar 정책.

**검토 대상 결과:** Case별 service/sojourn/waiting annotation 및 interval 근거.

**PIX 계산 정의:**

- Case span과 observed service interval의 원시 증거가 있다.

**남은 차이·검증 범위:**

- Case 전체 service/sojourn/waiting을 올바른 overlap 모집단으로 결합해 삽입하는 전용 계산은 미구현이다.

**실제 함수·모델:** [statistics.measure_case_performance](../../../src/pix/case_centric/statistics.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_statistics.py](../../../tests/case_centric/test_statistics.py)

</details>

## CC-FILTERING

**Explicit case/event/path selection and sampling**

### PM-DATA-022

**업무 질문:** 원하는 시작·종료 활동의 case만 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_start_activities`, `pm4py.filtering.filter_end_activities`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case log와 허용/제외 시작·종료 활동 집합.

**검토 대상 결과:** 조건을 만족하는 전체 case들과 선택 근거.

**PIX 계산 정의:**

- Source boundary, direct/eventual relation과 resource set 기반 four-eyes 등 typed predicate 및 witness.

**남은 차이·검증 범위:**

- Unknown을 positive/negative truth로 바꾸지 않는다. 모든 upstream repeated-activity pairing/option 동등성은 미검증.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-023

**업무 질문:** 이벤트·case 속성 값과 출현 비율에 따라 로그를 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_log_relative_occurrence_event_attribute`, `pm4py.filtering.filter_event_attribute_values`, `pm4py.filtering.filter_trace_attribute_values`, `pm4py.algo.filtering.log.attributes.attributes_filter.apply_numeric` 외 3개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Event/case 속성 조건, 수치 구간 또는 출현 비율 threshold.

**검토 대상 결과:** 조건에 따른 event slice 또는 전체 case sublog.

**PIX 계산 정의:**

- Typed event/case predicate, explicit occurrence denominator, variant frequency/top-k/coverage, time span, count/duration 및 path gap 선택.

**남은 차이·검증 범위:**

- 자동 값별 frequency/threshold, arbitrary trace-date attribute, business time, 임의 attribute repetition, service-start path basis는 별도 잔여다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-024

**업무 질문:** 어떤 variant를 남기고 빈도·coverage를 어떻게 제한하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_variants`, `pm4py.filtering.filter_variants_top_k`, `pm4py.filtering.filter_variants_by_coverage_percentage`, `pm4py.algo.filtering.log.variants.variants_filter.filter_variants_by_maximum_coverage_percentage` 외 3개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Variant별 case 집합, top-k·개별/누적 coverage 조건.

**검토 대상 결과:** 선택 variant의 sublog와 coverage·동률 처리 정보.

**PIX 계산 정의:**

- Typed event/case predicate, explicit occurrence denominator, variant frequency/top-k/coverage, time span, count/duration 및 path gap 선택.

**남은 차이·검증 범위:**

- 자동 값별 frequency/threshold, arbitrary trace-date attribute, business time, 임의 attribute repetition, service-start path basis는 별도 잔여다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-025

**업무 질문:** 직접 또는 나중에 이어지는 특정 활동 관계를 가진 case를 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_directly_follows_relation`, `pm4py.filtering.filter_eventually_follows_relation`, `pm4py.algo.filtering.log.ltl.ltl_checker.A_next_B_next_C`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동쌍/세 활동 관계와 인접·eventual 정책.

**검토 대상 결과:** 관계 조건을 만족/위반하는 case sublog.

**PIX 계산 정의:**

- Source boundary, direct/eventual relation과 resource set 기반 four-eyes 등 typed predicate 및 witness.

**남은 차이·검증 범위:**

- Unknown을 positive/negative truth로 바꾸지 않는다. 모든 upstream repeated-activity pairing/option 동등성은 미검증.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-026

**업무 질문:** 시간창에 포함·교차·시작·종료하는 case 또는 event를 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_time_range`, `pm4py.algo.filtering.log.timestamp.timestamp_filter.filter_on_trace_attribute`, `pm4py.algo.filtering.log.timestamp.timestamp_filter.filter_traces_attribute_in_timeframe`, `pm4py.algo.filtering.log.timestamp.timestamp_filter.filter_traces_starting_in_timeframe` 외 1개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Event/case 시각, 시간창과 contained/intersect/start/end mode.

**검토 대상 결과:** 시간 조건에 따른 case/event 선택과 잘린 경계.

**PIX 계산 정의:**

- Typed event/case predicate, explicit occurrence denominator, variant frequency/top-k/coverage, time span, count/duration 및 path gap 선택.

**남은 차이·검증 범위:**

- 자동 값별 frequency/threshold, arbitrary trace-date attribute, business time, 임의 attribute repetition, service-start path basis는 별도 잔여다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-027

**업무 질문:** 두 활동 사이·prefix·suffix·지정 부분열을 추출할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_between`, `pm4py.filtering.filter_prefixes`, `pm4py.filtering.filter_suffixes`, `pm4py.filtering.filter_trace_segments`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열, 경계 활동·prefix/suffix·부분열 조건.

**검토 대상 결과:** 추출한 구간 또는 선택 case와 원본 event 대응.

**PIX 계산 정의:**

- prefix/suffix/between/activity split/consecutive activity 또는 timestamp segment.

**남은 차이·검증 범위:**

- 실제 event fact를 집계·deduplicate하여 merge하지 않는다. 비연속 동률 grouping, wildcard/noncontiguous grammar는 미구현이다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py), [filtering.slice_cases](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-028

**업무 질문:** 길이·기간·재작업 횟수로 case를 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_case_size`, `pm4py.filtering.filter_case_performance`, `pm4py.filtering.filter_activities_rework`, `pm4py.algo.filtering.log.cases.case_filter.filter_on_ncases`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case별 길이·기간·반복 횟수, 개수/구간 조건.

**검토 대상 결과:** 조건에 맞는 case sublog와 제외 사유.

**PIX 계산 정의:**

- Typed event/case predicate, explicit occurrence denominator, variant frequency/top-k/coverage, time span, count/duration 및 path gap 선택.

**남은 차이·검증 범위:**

- 자동 값별 frequency/threshold, arbitrary trace-date attribute, business time, 임의 attribute repetition, service-start path basis는 별도 잔여다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-029

**업무 질문:** 특정 경로에 너무 오래 걸리는 case를 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_paths_performance`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case의 활동쌍 occurrence와 기간 threshold.

**검토 대상 결과:** 선택 경로의 성능 조건을 만족하는 case들.

**PIX 계산 정의:**

- Typed event/case predicate, explicit occurrence denominator, variant frequency/top-k/coverage, time span, count/duration 및 path gap 선택.

**남은 차이·검증 범위:**

- 자동 값별 frequency/threshold, arbitrary trace-date attribute, business time, 임의 attribute repetition, service-start path basis는 별도 잔여다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-030

**업무 질문:** 동일 활동을 서로 다른 사람이 처리하거나 업무 분리가 지켜지는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_four_eyes_principle`, `pm4py.filtering.filter_activity_done_different_resources`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열과 resource 속성, 업무 분리 대상 활동.

**검토 대상 결과:** Four-eyes/다른 수행자 조건의 만족·위반 case.

**PIX 계산 정의:**

- Source boundary, direct/eventual relation과 resource set 기반 four-eyes 등 typed predicate 및 witness.

**남은 차이·검증 범위:**

- Unknown을 positive/negative truth로 바꾸지 않는다. 모든 upstream repeated-activity pairing/option 동등성은 미검증.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-031

**업무 질문:** 연속·동률 이벤트를 묶거나 활동 발생을 기준으로 case를 분할할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.filtering.pandas.activity_split.activity_split_filter.apply`, `pm4py.algo.filtering.pandas.consecutive_act_case_grouping.consecutive_act_case_grouping_filter.apply`, `pm4py.algo.filtering.pandas.timestamp_case_grouping.timestamp_case_grouping_filter.apply`, `pm4py.algo.filtering.pandas.starts_with.starts_with_filter.apply` 외 1개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열·timestamp와 그룹/분할 또는 variant prefix/suffix 조건.

**검토 대상 결과:** 묶음·분할·선택된 case와 원본 event lineage.

**PIX 계산 정의:**

- prefix/suffix/between/activity split/consecutive activity 또는 timestamp segment.

**남은 차이·검증 범위:**

- 실제 event fact를 집계·deduplicate하여 merge하지 않는다. 비연속 동률 grouping, wildcard/noncontiguous grammar는 미구현이다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py), [filtering.slice_cases](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-DATA-032

**업무 질문:** DFG의 잦은 활동·경로와 특정 활동 주변 연결만 남길 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_dfg_activities_percentage`, `pm4py.filtering.filter_dfg_paths_percentage`, `pm4py.algo.filtering.dfg.dfg_filtering.filter_dfg_keep_connected`, `pm4py.algo.filtering.dfg.dfg_filtering.filter_dfg_to_activity` 외 3개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 빈도 DFG·시작/종료 빈도와 활동/경로/연결성 조건.

**검토 대상 결과:** 필터된 DFG 및 제거·유지된 원본 노드/edge 근거.

**PIX 계산 정의:**

- DFG frequency rank pruning, explicit source/end directed connectivity and selection witnesses.

**남은 차이·검증 범위:**

- Graph view retains source counts, not a new event-log frequency estimate; all reference default threshold/tie policies remain unverified.

**실제 함수·모델:** [dfg_filtering.filter_dfg](../../../src/pix/case_centric/dfg_filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_dfg_filtering.py](../../../tests/case_centric/test_dfg_filtering.py)

</details>

### PM-UTIL-001

**업무 질문:** 사용자가 지정한 조건으로 case·event를 고르고 원본 근거를 유지할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.hof.filter_log`, `pm4py.hof.filter_trace`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** EventLog·EventStream·Trace와 사용자 predicate.

**검토 대상 결과:** 조건을 만족하는 case 또는 event로 구성한 로그·trace.

**PIX 계산 정의:**

- 선언된 predicate와 검증 가능한 선택 증거·원본 보존 materialization.

**남은 차이·검증 범위:**

- 임의 callable predicate를 그대로 실행하는 upstream HOF 계약은 지원하지 않는다.

**실제 함수·모델:** [filtering.filter_case_log](../../../src/pix/case_centric/filtering.py), [filtering.materialize_case_selection](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

### PM-UTIL-002

**업무 질문:** 활동 순서와 case 순서를 사용자가 지정한 키로 바꾸되 가정을 기록할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.hof.sort_log`, `pm4py.hof.sort_trace`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·trace, 정렬 키 함수와 역순 옵션.

**검토 대상 결과:** case 또는 event의 순서를 재정렬한 로그·trace.

**PIX 계산 정의:**

- 명시 timestamp/string/numeric key·null/tie/reverse/empty-case 정책으로 case 내부를 안정 정렬하고 선택적으로 case를 정렬한다. 원래 위치와 tie group을 보존하며 materialization은 원본으로 재검증한다.

**남은 차이·검증 범위:**

- 정렬을 인과 순서로 해석하지 않는다. 임의 lambda와 전체 flattened stream 재정렬은 지원하지 않으며 PM4Py의 empty-case 삭제를 재현하지 않는다.

**실제 함수·모델:** [transformations.materialize_case_sort](../../../src/pix/case_centric/transformations.py), [transformations.sort_case_log](../../../src/pix/case_centric/transformations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_transformations.py](../../../tests/case_centric/test_transformations.py)

</details>

### PM-UTIL-007

**업무 질문:** case 또는 event를 재현 가능한 표본으로 뽑을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.utils.sample_cases`, `pm4py.utils.sample_events`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·OCEL, 표본 단위와 크기.

**검토 대상 결과:** 선택한 case 또는 event와 그에 따른 로그.

**PIX 계산 정의:**

- seeded case/global-event without-replacement sample; output source-order와 원본 ID 보존.

**남은 차이·검증 범위:**

- Random algorithm의 모든 Python version 간 동일성은 미검증. Oversize count는 clip 대신 invalid_input이다.

**실제 함수·모델:** [filtering.sample_cases](../../../src/pix/case_centric/filtering.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_filtering.py](../../../tests/case_centric/test_filtering.py)

</details>

## CC-INTERVALS

**Lifecycle pairing and case interval views**

### PM-DATA-035

**업무 질문:** Case의 인접 이벤트 사이 시간 구간을 추출할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_log_to_time_intervals`, `pm4py.algo.transformation.log_to_interval_tree.variants.open_paths.log_to_intervals`, `pm4py.algo.transformation.log_to_interval_tree.variants.open_paths.interval_to_tree`

**참조 선택지:** `OPEN_PATHS`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 인접 event의 complete·다음 start와 선택 활동쌍.

**검토 대상 결과:** 인접 open-path interval 목록과 event 대응.

**PIX 계산 정의:**

- 원본 인접 completion→explicit-start 또는 명시 completion→completion 구간과 unknown 상태.

**남은 차이·검증 범위:**

- Interval-tree index와 implicit source sorting/fallback는 미구현이다.

**실제 함수·모델:** [lifecycle.derive_adjacent_intervals](../../../src/pix/case_centric/lifecycle.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_lifecycle.py](../../../tests/case_centric/test_lifecycle.py)

</details>

### PM-DATA-036

**업무 질문:** Lifecycle 이벤트를 실행 interval로 짝짓고 다시 lifecycle로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.log.util.interval_lifecycle.to_interval`, `pm4py.objects.log.util.interval_lifecycle.to_lifecycle`, `pm4py.objects.log.util.interval_lifecycle.assign_lead_cycle_time`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Lifecycle start/complete log 또는 interval log, instance key와 calendar.

**검토 대상 결과:** 대응시킨 실행 구간 또는 lifecycle log와 lead/cycle-time annotation.

**PIX 계산 정의:**

- source-order start/complete pairing; ambiguous/FIFO/LIFO/typed instance 정책과 원본 sidecar 복원.

**남은 차이·검증 범위:**

- 임의 interval→synthetic lifecycle 로그, lead/cycle annotation과 calendar는 미구현이다.

**실제 함수·모델:** [lifecycle.pair_lifecycle_events](../../../src/pix/case_centric/lifecycle.py), [lifecycle.restore_lifecycle_events](../../../src/pix/case_centric/lifecycle.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_lifecycle.py](../../../tests/case_centric/test_lifecycle.py)

</details>

## CC-TRANSFORMS

**Case graph, synthetic boundaries, classifiers, contextual labels and relational merge**

### PM-DATA-034

**업무 질문:** Case 로그의 이벤트·자원 관계를 graph로 볼 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_log_to_networkx`

**참조 선택지:** `TO_NX`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case log와 DF·case/event 속성 노드 포함 설정.

**검토 대상 결과:** Event/case/attribute 노드 및 typed relation graph.

**PIX 계산 정의:**

- Typed case/event/attribute node와 event-case/source-DFG/attribute 관계를 계산하며 value namespace와 다중 edge를 보존한다.

**남은 차이·검증 범위:**

- 반환값은 native graph이며 NetworkX 객체 호환이 아니다. 네임스페이스 충돌·동일 endpoint attribute edge 덮어쓰기를 재현하지 않는다.

**실제 함수·모델:** [transformations.case_log_to_graph](../../../src/pix/case_centric/transformations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_transformations.py](../../../tests/case_centric/test_transformations.py)

</details>

### PM-DATA-037

**업무 질문:** 분석용 가상 시작·종료 이벤트를 명시적으로 추가할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.insert_artificial_start_end`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case log와 가상 start/end 활동명·시각 부여 정책.

**검토 대상 결과:** 원본과 가상 이벤트가 구분된 분석 view 및 ID lineage.

**PIX 계산 정의:**

- 명시 collision/empty-case 정책과 none/endpoint/outside timestamp 정책으로 별도 synthetic 시작·끝 event를 생성한다. 원본과 합성 사실을 표시하고 global resource defaults를 null override한다.

**남은 차이·검증 범위:**

- 기본값은 timestamp를 생성하지 않는다. 참조 trace mutation·자동 1초 offset과 다르며 합성 boundary를 원래 관측으로 계산하면 안 된다.

**실제 함수·모델:** [transformations.insert_case_boundaries](../../../src/pix/case_centric/transformations.py), [transformations.materialize_case_boundaries](../../../src/pix/case_centric/transformations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_transformations.py](../../../tests/case_centric/test_transformations.py)

</details>

### PM-DATA-039

**업무 질문:** 동일 활동 라벨을 전후 문맥에 따라 구분할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.label_splitting.algorithm.apply`

**참조 선택지:** `CONTEXTUAL`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 활동열, 대상 활동·prefix/suffix 길이·edge threshold.

**검토 대상 결과:** 문맥별로 분리된 activity label과 원본 event 대응.

**PIX 계산 정의:**

- 활동별 bounded prefix/suffix 문맥의 정규화 token edit similarity graph에서 exact-rational global weighted greedy modularity를 계산한다. Combined/sided context를 구분하며 fit/apply와 미관측 context를 별도 처리한다.

**남은 차이·검증 범위:**

- Greedy modularity는 전역 최대 모듈성 증명이 아니다. 참조 float/tie·in-place relabel과 다르며 새로운 context에 의미를 추측해 부여하지 않는다. 학습 문맥이 실제 업무 종류라는 인과 주장도 하지 않는다.

**실제 함수·모델:** [label_splitting.apply_label_splitting](../../../src/pix/case_centric/label_splitting.py), [label_splitting.fit_label_splitting](../../../src/pix/case_centric/label_splitting.py), [label_splitting.materialize_label_splitting](../../../src/pix/case_centric/label_splitting.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_label_splitting.py](../../../tests/case_centric/test_label_splitting.py)

</details>

### PM-DATA-040

**업무 질문:** 서로 연관된 case 관계표를 사용해 두 로그를 결합할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.merging.case_relations.algorithm.apply`

**참조 선택지:** `PANDAS`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 두 case table과 left/right case 관계표, timestamp/key 설정.

**검토 대상 결과:** 관계로 결합한 case table과 원본 case/event lineage.

**PIX 계산 정의:**

- 명시 left-right case relation에 따라 right event occurrence를 left case에 병합한다. 복수 relation과 duplicate 정책, unlinked case 및 시간 tie를 기록하며 원본 global 환경은 각 side에 보존한다.

**남은 차이·검증 범위:**

- 관계로 반복된 occurrence와 고유 source event 수를 구별한다. 파생 case를 원래 하나의 case로 간주하지 않으며 두 입력의 충돌하는 globals를 암묵적으로 합치지 않는다.

**실제 함수·모델:** [transformations.materialize_merged_cases](../../../src/pix/case_centric/transformations.py), [transformations.merge_linked_cases](../../../src/pix/case_centric/transformations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_transformations.py](../../../tests/case_centric/test_transformations.py)

</details>

### PM-UTIL-005

**업무 질문:** 복합 classifier를 적용해 활동의 정체성을 정할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.utils.set_classifier`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그와 classifier 이름 또는 속성 목록.

**검토 대상 결과:** 복합 활동 값을 추가하고 activity property를 바꾼 참조 로그.

**PIX 계산 정의:**

- 기존 composite classifier와 trace 활동 투영이 동작한다.

**남은 차이·검증 범위:**

- in-place set_classifier와 임의 event attribute를 모든 타입 그대로 sequence로 투영하는 반환 계약은 별도다.

**실제 함수·모델:** [adapters.case_traces](../../../src/pix/event_log/adapters.py).

**관련 테스트:** registry에 연결된 파일이 없다.

### PM-UTIL-006

**업무 질문:** case별 특정 이벤트 속성 값을 순서대로 읽을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.utils.project_on_event_attribute`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그와 case 식별 열 및 투영할 event 속성.

**검토 대상 결과:** case마다 선택 속성 값의 순서열.

**PIX 계산 정의:**

- 기존 composite classifier와 trace 활동 투영이 동작한다.

**남은 차이·검증 범위:**

- in-place set_classifier와 임의 event attribute를 모든 타입 그대로 sequence로 투영하는 반환 계약은 별도다.

**실제 함수·모델:** [adapters.case_traces](../../../src/pix/event_log/adapters.py).

**관련 테스트:** registry에 연결된 파일이 없다.

## CC-FEATURE-DATASET

**Leakage-aware split, prefixes, enriched outcomes and targets**

### PM-ADV-001

**업무 질문:** 전체 case를 보존하면서 학습·검증 집합을 나누는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.split_train_test`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 단위 이벤트 로그와 학습 비율·분할 seed·그룹 제약.

**검토 대상 결과:** Case가 분할되지 않는 학습/검증 로그와 집합 구성 근거.

**PIX 계산 정의:**

- CaseSplitSpec: source-order invariant seeded hash rank, exact floor sizes for train/validation, remainder test; no case overlap.

**남은 차이·검증 범위:**

- Not reference per-case random Bernoulli allocation; chronological, stratified, shared-object/group leakage splitting absent.

**실제 함수·모델:** [features.split_cases](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-002

**업무 질문:** 예측 시점까지 관측된 prefix만 추출하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.get_prefixes_from_log`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 로그와 prefix 길이 또는 관측 cutoff.

**검토 대상 결과:** 원본 순서를 유지하며 관측 범위에서 잘린 case별 prefix.

**PIX 계산 정의:**

- PrefixSpec: explicit min/max length including zero; original order; input fields separated from targets; materialization caps reject incomplete dataset.

**남은 차이·검증 범위:**

- No event-time cutoff or censoring model. Full observed case endpoint is treated as terminal, not certified business completion.

**실제 함수·모델:** [features.prefix_dataset](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-003

**업무 질문:** 전체 case의 결과와 처리·대기·도착 정보를 학습 표에 붙이는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.extract_outcome_enriched_dataframe`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 완료 결과를 포함한 case 로그와 활동·시간·case 키.

**검토 대상 결과:** Case 결과·도착/완료율·service/waiting 등을 결합한 학습 표.

**PIX 계산 정의:**

- Retrospective case span/service/nonservice/interarrival/interfinish aggregates exist in temporal windows; event prefix timing exists.

**남은 차이·검증 범위:**

- Dedicated per-case outcome-enriched dataframe/payload and complete PM outcome columns not implemented; window aggregation must not be advertised as equivalent output.

**실제 함수·모델:** [features.temporal_features](../../../src/pix/case_centric/features.py), [features.temporal_window_features](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-011

**업무 질문:** 관측 prefix 다음 활동을 target으로 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.extract_target_vector`

**참조 선택지:** `NEXT_ACTIVITY`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 순서가 있는 case 로그와 다음 활동 label 정책.

**검토 대상 결과:** 각 관측 위치의 다음 활동 target과 class vocabulary.

**PIX 계산 정의:**

- PredictionTarget next_activity separate from input with explicit terminal flag; complete prefix has None next activity.

**남은 차이·검증 범위:**

- Observed log endpoint rather than external completion/censoring status; no learned classifier.

**실제 함수·모델:** [features.prefix_dataset](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-012

**업무 질문:** 다음 이벤트까지 시간과 완료까지 남은 시간을 target으로 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.extract_target_vector`

**참조 선택지:** `NEXT_TIME`, `REMAINING_TIME`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Timestamp가 있는 case 로그와 다음 시각/잔여 시간 target 선택.

**검토 대상 결과:** 각 관측 위치의 시간 target과 단위·종료/미완료 처리 정보.

**PIX 계산 정의:**

- PredictionTarget next/remaining seconds; missing/decreasing time unknown; terminal next-time absent.

**남은 차이·검증 범위:**

- No right-censoring or business completion metadata; not a learned predictor; arbitrary PM target timestamp/default parity unverified.

**실제 함수·모델:** [features.prefix_dataset](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

## CC-FEATURES

**Trace, event, temporal and conformance encoders**

### PM-ADV-004

**업무 질문:** Case 하나를 활동·속성·시간 등의 수치 feature 벡터로 표현하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.extract_features_dataframe`

**참조 선택지:** `TRACE_BASED`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 로그와 활동·속성 선택, feature 옵션 및 학습 vocabulary.

**검토 대상 결과:** Case별 수치 feature 행렬과 열 이름·단위·결측 정보.

**PIX 계산 정의:**

- FeatureSpec(level="trace"): fitted activity/n-gram plus selected numeric and type-tagged categorical attributes; train-only fit and frozen transform.

**남은 차이·검증 범위:**

- All PM trace engineered fields and text context/default vocabulary conventions not mapped one-to-one.

**실제 함수·모델:** [features.fit_features](../../../src/pix/case_centric/features.py), [features.transform_features](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-005

**업무 질문:** Case 안의 각 이벤트를 순서가 유지된 feature 벡터로 표현하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.trace_encodings.algorithm.apply`

**참조 선택지:** `EVENT_BASED`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 순서가 있는 case 이벤트와 event 속성·encoding 설정.

**검토 대상 결과:** Case별 이벤트 feature sequence와 열 이름·길이/결측 정보.

**PIX 계산 정의:**

- FeatureSpec(level="event"): one document per event; selected event/global attributes; explicit prefix temporal row.

**남은 차이·검증 범위:**

- PM padded case-event tensor and complete event encoder schema not reproduced.

**실제 함수·모델:** [features.fit_features](../../../src/pix/case_centric/features.py), [features.temporal_features](../../../src/pix/case_centric/features.py), [features.transform_features](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-006

**업무 질문:** 시간 구간별 프로세스 feature와 변화 시계열을 만드는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.extract_temporal_features_dataframe`

**참조 선택지:** `TEMPORAL`, `TEMPORAL_LAZY`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 시간 속성이 있는 로그와 구간·집계·실행 backend 설정.

**검토 대상 결과:** 시간 구간별 process feature 표와 구간·표본 정보.

**PIX 계산 정의:**

- Fixed UTC-anchored half-open windows; counts, resources, rework, retrospective case-weighted spans/service/union-nonservice, boundary gaps and valid denominators.

**남은 차이·검증 범위:**

- TEMPORAL/TEMPORAL_LAZY backend semantics and calendar bucket/default columns not fully matched; no lazy execution implementation.

**실제 함수·모델:** [features.temporal_window_features](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-007

**업무 질문:** 활동 토큰과 n-gram을 count·binary·TF-IDF 형태로 인코딩하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.trace_encodings.algorithm.apply`

**참조 선택지:** `COUNT2VEC`, `N_GRAMS`, `ONE_HOT`, `TF_IDF`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace 활동 토큰과 n-gram·vocabulary·가중치/정규화 설정.

**검토 대상 결과:** Count·binary·TF-IDF trace 행렬과 학습한 vocabulary.

**PIX 계산 정의:**

- FeatureSpec encoding count/binary/tfidf; contiguous source-order ngrams; smooth IDF log((1+documents)/(1+df))+1 and optional activity-block L2; count unigram implements Count2Vec activity baseline.

**남은 차이·검증 범위:**

- Composite event-attribute text tokens and trace-context tokens, sklearn sparse/vectorizer import, reference tokenization/default compatibility remain.

**실제 함수·모델:** [features.fit_features](../../../src/pix/case_centric/features.py), [features.transform_features](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

### PM-ADV-010

**업무 질문:** Alignment와 token replay 진단을 학습 feature로 바꾸는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.trace_encodings.algorithm.apply`

**참조 선택지:** `ALIGNMENTS`, `TOKEN_REPLAY`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그와 Petri net 또는 모델 발견 설정, replay/alignment 옵션.

**검토 대상 결과:** Case별 alignment/token 진단 feature 행렬과 모델·열 mapping.

**PIX 계산 정의:**

- ModelFeatureSpec method alignment: cost plus sync/log/model/silent move counts; token_replay: missing/remaining/consumed/produced/deviation counts; incomplete cases retain None.

**남은 차이·검증 범위:**

- Reference full transition/place coordinate encodings and every alignment/replay profile not covered; current aggregate vectors differ.

**실제 함수·모델:** [features.model_features](../../../src/pix/case_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_features.py](../../../tests/case_centric/test_features.py)

</details>

## CC-EMBEDDINGS

**Word/Doc2Vec and transformer embeddings; learned models remain explicit**

### PM-ADV-008

**업무 질문:** Trace를 학습된 Word2Vec·Doc2Vec 벡터로 표현하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.trace_encodings.algorithm.apply`

**참조 선택지:** `WORD2VEC`, `DOC2VEC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace 토큰과 Word2Vec/Doc2Vec 모델·학습 또는 추론 설정.

**검토 대상 결과:** Trace별 embedding 벡터와 사용 모델·집계 설정.

**PIX 계산 정의:**

- EmbeddingSpec skipgram/cbow/pv_dbow/pv_dm: native negative-sampling SGD; fixed trained weights, mean/sum word pooling, frozen-weight document inference.

**남은 차이·검증 범위:**

- No hierarchical softmax, subsampling, stochastic shrinking window, complete Gensim option/model compatibility, composite event/trace text or prediction-quality validation.

**실제 함수·모델:** [embeddings.fit_embeddings](../../../src/pix/case_centric/embeddings.py), [embeddings.transform_embeddings](../../../src/pix/case_centric/embeddings.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_embeddings.py](../../../tests/case_centric/test_embeddings.py)
- [tests/case_centric/test_transformer_embeddings.py](../../../tests/case_centric/test_transformer_embeddings.py)

</details>

### PM-ADV-009

**업무 질문:** Case·event 문맥을 transformer embedding으로 표현하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.trace_encodings.algorithm.apply`, `pm4py.algo.transformation.to_embeddings.algorithm.apply`

**참조 선택지:** `BERT`, `CASES_TRANSFORMERS`, `EVENTS_TRANSFORMERS`.

**현재 상태:** `external_runtime_unverified` — 실제 외부 runtime 실행 근거가 부족한 경로. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case/event 텍스트 표현과 transformer 모델·embedding 설정.

**검토 대상 결과:** 표본별 embedding 벡터와 표본 ID·모델 식별 정보.

**PIX 계산 정의:**

- pix.case_centric.transformer_embeddings.transformer_embeddings: optional local SentenceTransformer trace/event JSON-activity text inference; checkpoint digest and offline-only loader; no fabricated vectors.

**남은 차이·검증 범위:**

- Real checkpoint/model execution unverified; only adapter test double tested. Checkpoint may be BERT or other encoder; no full PM BERT/case/event transformer text, model or numerical parity.

**실제 함수·모델:** [transformer_embeddings.transformer_embeddings](../../../src/pix/case_centric/transformer_embeddings.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_embeddings.py](../../../tests/case_centric/test_embeddings.py)
- [tests/case_centric/test_transformer_embeddings.py](../../../tests/case_centric/test_transformer_embeddings.py)

</details>

### PM-ADV-018

**업무 질문:** 질문 문장과 가장 유사한 case·event를 embedding으로 선택하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.trace_encodings.algorithm.keep_top_k_per_similarity`, `pm4py.algo.transformation.to_embeddings.algorithm.keep_top_k_per_similarity`

**참조 선택지:** `CASES_TRANSFORMERS`, `EVENTS_TRANSFORMERS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case/event 표본·질문 문장·embedding 모델과 k.

**검토 대상 결과:** 질문과 유사한 상위 k개 case/event 및 유사도 선택 근거.

**PIX 계산 정의:**

- Exact exhaustive finite vector top-k using cosine/dot/Euclidean, tie policy and pair cap; coordinate/encoder/model/transform/training provenance must match.
- Adapts native learned, fixed-feature and local-transformer trace matrices or accepts explicitly declared corpus/query vectors; no fitting during query.

**남은 차이·검증 범위:**

- No automatic free-text query neural encoding/end-to-end neural execution validation. Direct event-level encoder outputs are rejected pending explicit case pooling. No full PM case/event text/filter/default parity.

**실제 함수·모델:** [embedding_retrieval.as_embedding_batch](../../../src/pix/case_centric/embedding_retrieval.py), [embedding_retrieval.retrieve_embedding_neighbors](../../../src/pix/case_centric/embedding_retrieval.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/case_centric/test_embedding_retrieval.py](../../../tests/case_centric/test_embedding_retrieval.py)
- [tests/case_centric/test_embeddings.py](../../../tests/case_centric/test_embeddings.py)
- [tests/case_centric/test_transformer_embeddings.py](../../../tests/case_centric/test_transformer_embeddings.py)

</details>

## CC-DECISION

**Decision table, tree, guard and data-net mining**

### PM-ADV-013

**업무 질문:** 분기 직전 어떤 데이터가 경로 선택과 연관되는지 설명하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.decision_mining.algorithm.create_data_petri_nets_with_decisions`, `pm4py.algo.decision_mining.algorithm.get_decision_tree`, `pm4py.algo.decision_mining.algorithm.get_decisions_table`, `pm4py.algo.decision_mining.algorithm.get_decision_points` 외 4개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·Petri net·초기/최종 marking과 관측 속성·결정 학습 설정.

**검토 대상 결과:** 분기별 학습 표·decision tree/규칙 또는 결정 조건을 붙인 모델.

**PIX 계산 정의:**

- Structural multi-outgoing places; alignment/replay firing-witness decision observations; strictly previous numeric event features or explicitly declared initial case features.
- Native CART model per decision point; typed DataPetriNet transition guards; true/false/unknown guard logic composed with token enabling; only true allows firing.

**남은 차이·검증 범위:**

- Categorical decision feature encoding, complete PM default/ambiguity semantics and held-out predictive validity remain unverified. Selected witness is not causal identification or consensus over all optimal alignments. Reset/inhibitor semantics are outside this module.

**실제 함수·모델:** [decision_mining.discover_decision_points](../../../src/pix/case_centric/decision_mining.py), [decision_mining.evaluate_data_guards](../../../src/pix/case_centric/decision_mining.py), [decision_mining.extract_decision_table](../../../src/pix/case_centric/decision_mining.py), [decision_mining.fire_data_transition](../../../src/pix/case_centric/decision_mining.py), [decision_mining.mine_data_petri_net](../../../src/pix/case_centric/decision_mining.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_advanced.py](../../../tests/case_centric/test_advanced.py)
- [tests/test_decision_mining.py](../../../tests/test_decision_mining.py)

</details>

## CC-CLUSTERING

**Profile and hierarchical sublog clustering**

### PM-ADV-014

**업무 질문:** Case feature profile로 유사한 사례를 군집화하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.cluster_log`

**참조 선택지:** `SKLEARN_PROFILES`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 로그와 feature·정규화·군집 estimator 설정.

**검토 대상 결과:** 군집별 하위 로그와 case별 군집 대응·설정.

**PIX 계산 정의:**

- Native count-profile farthest-first Lloyd K-means, exact rational centroid/inertia; case-vector Euclidean and edit/DFG-cosine agglomeration with single/complete/average linkage.

**남은 차이·검증 범위:**

- Not all sklearn estimators/scaling/random initialization; no global K-means optimality claim or SKLEARN_PROFILES exact numerical parity.

**실제 함수·모델:** [advanced.cluster_case_profiles](../../../src/pix/case_centric/advanced.py), [advanced.cluster_cases](../../../src/pix/case_centric/advanced.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_advanced.py](../../../tests/case_centric/test_advanced.py)

</details>

### PM-ADV-015

**업무 질문:** Trace 속성별 하위 로그를 행동 거리로 군집화하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.clustering.trace_attribute_driven.algorithm.bfs`

**참조 선택지:** `VARIANT_DMM_LEVEN`, `VARIANT_AVG_LEVEN`, `VARIANT_DMM_VEC`, `VARIANT_AVG_VEC`, `DFG`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Trace 속성으로 구분된 로그 집단과 거리·linkage variant.

**검토 대상 결과:** 집단 간 거리와 계층적 군집 결과·구성 사례.

**PIX 계산 정의:**

- Typed primitive trace attribute sublogs; mean raw/normalized edit across all case pairs or aggregated DFG cosine; explicit linkage.

**남은 차이·검증 범위:**

- VARIANT_DMM_LEVEN/AVG_LEVEN/DMM_VEC/AVG_VEC definitions and weighting not reproduced one-to-one; available distances are PIX profiles.

**실제 함수·모델:** [advanced.cluster_case_attribute_groups](../../../src/pix/case_centric/advanced.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_advanced.py](../../../tests/case_centric/test_advanced.py)

</details>

## CC-DRIFT

**Bose relation-distribution concept drift**

### PM-ADV-016

**업무 질문:** 시간에 따라 프로세스 관계 분포가 바뀌는 구간을 찾는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.concept_drift.algorithm.apply`

**참조 선택지:** `BOSE`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 순서/시간이 있는 로그와 sublog·window·permutation·검정 설정.

**검토 대상 결과:** 변화 후보 지점·관련 p-value 및 구간별 로그.

**PIX 계산 정의:**

- Bose relation type count features (always/sometimes/never eventually-follows), adjacent sublog window squared mean difference; exact or seeded +1 Monte Carlo permutation tests.

**남은 차이·검증 범위:**

- Reference unseeded Monte Carlo/statistical defaults differ; no automatic chronology, multi-test guarantee, causal change attribution or detector-power validation.

**실제 함수·모델:** [advanced.detect_bose_drift](../../../src/pix/case_centric/advanced.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_advanced.py](../../../tests/case_centric/test_advanced.py)

</details>

## CC-LANGUAGE-DISTANCE

**Stochastic-language Earth Mover distance**

### PM-ADV-017

**업무 질문:** 두 로그·모델의 확률적 trace 언어가 얼마나 다른가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.analysis.compute_emd`

**참조 선택지:** `PYEMD`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 두 유한 확률 trace 언어와 trace 간 운송 비용 설정.

**검토 대상 결과:** 설정한 비용과 확률 질량에 대한 Earth Mover's Distance.

**PIX 계산 정의:**

- Exact rational balanced min-cost transport over explicit finite normalized trace languages, raw/max-length normalized edit ground distance; transport witnesses and residual rerouting.

**남은 차이·검증 범위:**

- Arbitrary model stochastic language extraction and unbounded-language treatment absent; PYEMD backend option/numerical equality not claimed.

**실제 함수·모델:** [advanced.compare_stochastic_languages](../../../src/pix/case_centric/advanced.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_advanced.py](../../../tests/case_centric/test_advanced.py)

</details>

## CC-ORGANIZATION

**Handover, joint work, subcontract, roles and resource diagnostics**

### PM-ORG-001

**업무 질문:** 누가 누구에게 업무를 인계하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.org.discover_handover_of_work_network`

**참조 선택지:** `HANDOVER_LOG`, `HANDOVER_PANDAS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Resource가 기록된 case 로그와 인계 거리·정규화 설정.

**검토 대상 결과:** 자원 간 handover 가중 network.

**PIX 계산 정의:**

- SocialNetworkSpec metric=handover: distance decay beta^(d-1), explicit self/normalization, missing-resource positions preserved.

**남은 차이·검증 범위:**

- Source/default/backend denominators and bug compatibility not asserted.

**실제 함수·모델:** [organization.discover_social_network](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-002

**업무 질문:** 같은 case에서 어떤 자원들이 함께 일하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.org.discover_working_together_network`

**참조 선택지:** `WORKING_TOGETHER_LOG`, `WORKING_TOGETHER_PANDAS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Resource가 기록된 case 로그와 공동 참여 집계 설정.

**검토 대상 결과:** 같은 case에서 함께 일한 자원 쌍의 가중 network.

**PIX 계산 정의:**

- metric=working_together: unordered pair once per case, denominator includes empty cases.

**남은 차이·검증 범위:**

- PM LOG vs pandas denominators differ; PIX case denominator explicit, no forced parity.

**실제 함수·모델:** [organization.discover_social_network](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-003

**업무 질문:** 업무를 맡겼다가 돌아오는 subcontracting 관계는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.org.discover_subcontracting_network`

**참조 선택지:** `SUBCONTRACTING_LOG`, `SUBCONTRACTING_PANDAS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Resource 순서가 있는 case 로그와 subcontracting 거리 설정.

**검토 대상 결과:** 위임 후 돌아오는 자원 관계의 가중 network.

**PIX 계산 정의:**

- metric=subcontracting: each repeated/overlapping qualifying resource return, intervening occurrence weights beta^(d-2).

**남은 차이·검증 범위:**

- Pinned source can lose repeated return windows; PIX counts all; deliberate behavior correction requires semantic review.

**실제 함수·모델:** [organization.discover_social_network](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-004

**업무 질문:** 활동 구성을 기준으로 어떤 자원이 유사한가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.org.discover_activity_based_resource_similarity`

**참조 선택지:** `JOINTACTIVITIES_LOG`, `JOINTACTIVITIES_PANDAS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case 로그의 resource·activity와 유사도 설정.

**검토 대상 결과:** 자원별 활동 구성과 자원 쌍 유사도 network.

**PIX 계산 정의:**

- metric=joint_activities: Pearson or cosine activity-count vectors; undefined constant/zero vectors retain None.

**남은 차이·검증 범위:**

- Nonfinite/degenerate reference outputs not emulated; full option parity unverified.

**실제 함수·모델:** [organization.discover_social_network](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-005

**업무 질문:** 활동 집합을 수행하는 조직 역할을 발견하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.org.discover_organizational_roles`, `pm4py.algo.organizational_mining.roles.common.algorithm.get_sum_from_dictio_values`, `pm4py.algo.organizational_mining.roles.common.algorithm.normalize_role`, `pm4py.algo.organizational_mining.roles.common.algorithm.find_multiset_intersection` 외 5개(전체는 registry)

**참조 선택지:** `LOG`, `PANDAS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Resource×activity 빈도와 역할 병합 threshold.

**검토 대상 결과:** 활동·자원 구성으로 표현한 조직 역할 집합.

**PIX 계산 정의:**

- L1-normalized resource multiset Jaccard, greedy strict-threshold maximum merge, first-appearance tie ordering.

**남은 차이·검증 범위:**

- All reference input/backend/default compatibility not established; scalability unmeasured.

**실제 함수·모델:** [organization.discover_roles](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-006

**업무 질문:** 선택한 속성의 인계 network 빈도·시간을 분석하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.org.discover_network_analysis`

**참조 선택지:** `DATAFRAME`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그와 source/target 속성·edge 속성·시간 집계 설정.

**검토 대상 결과:** 속성 간 network와 edge별 빈도 또는 성능 값.

**PIX 계산 정의:**

- Explicit case or cross-case string joins; first/all future matching; event witnesses; frequency/time; fixed-offset weekly business slots/excluded dates.

**남은 차이·검증 범위:**

- Arbitrary numeric/object-valued nodes and named-zone DST-varying calendars absent.

**실제 함수·모델:** [organization.discover_attribute_network](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-007

**업무 질문:** 발견한 조직 집단의 focus·stake·coverage·기여를 진단하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.organizational_mining.local_diagnostics.algorithm.apply_from_clustering_or_roles`, `pm4py.algo.organizational_mining.local_diagnostics.algorithm.apply_from_group_attribute`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 로그와 조직 집단·역할 또는 clustering 결과.

**검토 대상 결과:** 집단별 focus·stake·coverage·member contribution 진단.

**PIX 계산 정의:**

- Explicit focus/stake/coverage/member-contribution formulas; raw counts and shares retained, overlapping groups independent.

**남은 차이·검증 범위:**

- Pinned local_diagnostics names/denominators differ; semantic choices still need domain validation.

**실제 함수·모델:** [organization.measure_organization](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-008

**업무 질문:** 자원별 활동 종류·빈도·완료 case와 기여 비율은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.organizational_mining.resource_profiles.algorithm.distinct_activities`, `pm4py.algo.organizational_mining.resource_profiles.algorithm.activity_frequency`, `pm4py.algo.organizational_mining.resource_profiles.algorithm.activity_completions`, `pm4py.algo.organizational_mining.resource_profiles.algorithm.case_completions` 외 1개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Resource가 기록된 로그와 자원·활동·시간창 선택.

**검토 대상 결과:** 자원별 활동/완료 case 집계와 해당 비율.

**PIX 계산 정의:**

- Observed activity counts/fractions, selected-case participation, observed endpoint completion proxy.

**남은 차이·검증 범위:**

- No business-termination inference; exact API/default compatibility unverified.

**실제 함수·모델:** [organization.measure_resource_profiles](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-009

**업무 질문:** 자원의 평균 workload와 multitasking 정도는 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.organizational_mining.resource_profiles.algorithm.average_workload`, `pm4py.algo.organizational_mining.resource_profiles.algorithm.multitasking`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 자원별 활동 interval 또는 시작 추정 정책과 시간창.

**검토 대상 결과:** 평균 workload·multitasking 및 그 시간 모집단.

**PIX 계산 정의:**

- Half-open multiplicity-preserving interval sweep: effort/window, effort/busy, overlap>=2/busy, peak concurrency.

**남은 차이·검증 범위:**

- Deliberately differs from source whole-event-overlap formula and duplicate collapsing; not same metric aliases.

**실제 함수·모델:** [organization.measure_resource_profiles](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-010

**업무 질문:** 자원이 수행한 활동·case의 평균 소요시간은 얼마인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.organizational_mining.resource_profiles.algorithm.average_duration_activity`, `pm4py.algo.organizational_mining.resource_profiles.algorithm.average_case_duration`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 시작/완료가 있는 로그와 자원·활동·시간창.

**검토 대상 결과:** 자원별 평균 활동 기간과 참여 case 기간.

**PIX 계산 정의:**

- Explicit-start activity durations, optional marked previous-event inference, observed completion-span; missing remains unknown.

**남은 차이·검증 범위:**

- No silent initial zero-duration or prior-event imputation, no lifecycle pairing; observed span is not service time.

**실제 함수·모델:** [organization.measure_resource_profiles](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

### PM-ORG-011

**업무 질문:** 자원 간 공동 참여와 사회적 위치를 수치화하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.organizational_mining.resource_profiles.algorithm.interaction_two_resources`, `pm4py.algo.organizational_mining.resource_profiles.algorithm.social_position`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Resource가 기록된 case 로그와 대상 자원·시간창.

**검토 대상 결과:** 자원 간 interaction 및 social position 수치.

**PIX 계산 정의:**

- Shared selected cases, participation fraction, coworker count/fraction over explicit resource population.

**남은 차이·검증 범위:**

- No broader graph-centrality suite inferred from social-position name; observed population/default equivalence unverified.

**실제 함수·모델:** [organization.measure_resource_profiles](../../../src/pix/case_centric/organization.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_organization.py](../../../tests/case_centric/test_organization.py)

</details>

## CC-SIMULATION

**Finite/random/stochastic classical playout and FIFO simulation**

### PM-SIM-001

**업무 질문:** Petri net이 허용하는 유한 실행을 생성·열거하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.sim.play_out`

**참조 선택지:** `BASIC_PLAYOUT`, `EXTENSIVE`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Petri net·초기/최종 marking과 생성 수·seed·탐색 한도.

**검토 대상 결과:** 생성하거나 열거한 trace와 완료·deadlock·한도 상태.

**PIX 계산 정의:**

- PlayoutSpec sampled weighted/random enabled transitions or exhaustive BFS quotient (marking, visible prefix); exact final marking acceptance and explicit limits.

**남은 차이·검증 범위:**

- Reference final-state stop lottery, alternative token semantics, timestamp export and all policy defaults absent. Exhaustive language quotient does not enumerate every silent path.

**실제 함수·모델:** [simulation.playout_petri_net](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

### PM-SIM-002

**업무 질문:** 확률과 시간 분포를 가진 Petri net 실행을 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.simulation.playout.petri_net.algorithm.apply`

**참조 선택지:** `STOCHASTIC_PLAYOUT`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Petri net·marking·stochastic map 및 seed/생성 설정.

**검토 대상 결과:** 분기와 처리시간을 표본 추출한 timestamp 포함 실행 로그.

**PIX 계산 정의:**

- Sampled transition_weights are relative choice weights; missing=1, all-zero uniform fallback.

**남은 차이·검증 범위:**

- No log-derived stochastic map fitting or final-stop policy compatibility. Reference STOCHASTIC_PLAYOUT selects weights and does not sample service durations; timed PN is separate scope.

**실제 함수·모델:** [simulation.playout_petri_net](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

### PM-SIM-003

**업무 질문:** Process tree로부터 무작위·전체·top-bottom 실행을 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.sim.play_out`

**참조 선택지:** `BASIC_PLAYOUT`, `EXTENSIVE`, `TOPBOTTOM`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Process tree와 playout variant·생성 수·loop/탐색 한도.

**검토 대상 결과:** Tree 의미에 따라 생성하거나 열거한 trace 집합.

**PIX 계산 정의:**

- Native tree-to-PN conversion then executable sampled/exhaustive playout; sequence/xor/parallel/loop/tau.

**남은 차이·검증 범위:**

- No BASIC/TOPBOTTOM tree-specific sampling distributions; neither uniform complete-trace sampling nor full tree variant parity.

**실제 함수·모델:** [simulation.playout_process_tree](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

### PM-SIM-004

**업무 질문:** DFG의 시작·끝·전이 빈도로 실행을 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.sim.play_out`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** DFG·시작/끝 빈도와 길이·수량·seed 제한.

**검토 대상 결과:** DFG 전이 확률에 따라 생성한 실행 로그.

**PIX 계산 정의:**

- enumerate_dfg: best-first complete Markov path probabilities with retained/excluded/pending mass; playout_dfg: distinct weighted sampled routes.

**남은 차이·검증 범위:**

- Reference CLASSIC is probability enumeration, not random sampler; DFG edge-coverage stop, integer apportionment and synthetic timestamps absent.

**실제 함수·모델:** [simulation.enumerate_dfg](../../../src/pix/case_centric/simulation.py), [simulation.playout_dfg](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

### PM-SIM-005

**업무 질문:** DFG 경로에 성능 시간을 붙여 실행을 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.simulation.playout.dfg.algorithm.apply`

**참조 선택지:** `PERFORMANCE`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 빈도/성능 DFG와 시작/끝 정보·시간 생성 설정.

**검토 대상 결과:** DFG 경로와 duration에 따른 timestamp 포함 로그.

**PIX 계산 정의:**

- Explicit per-activity durations and edge delays; fixed/uniform/exponential distributions; missing timing rejected, no invented case clock.

**남은 차이·검증 범위:**

- No reference inferred mean fitting or exact exponential edge-delta/default output profile parity.

**실제 함수·모델:** [simulation.playout_dfg](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

### PM-SIM-009

**업무 질문:** 자원 제약과 queue 아래에서 처리·대기 결과를 simulation하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.simulation.montecarlo.algorithm.apply`

**참조 선택지:** `PETRI_SEMAPH_FIFO`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 로그·Petri net·marking과 도착/처리 분포·자원/queue 설정.

**검토 대상 결과:** Simulation 실행 기록과 대기·처리·throughput 시나리오 결과.

**PIX 계산 정의:**

- Monte Carlo supplied sequential case routes/arrivals, nonpreemptive FIFO with resource pool capacities and supplied service distributions.

**남은 차이·검증 범위:**

- Not general concurrent Petri-net semaphore execution (PETRI_SEMAPH_FIFO); no multi-resource atomic acquisition, calendars, preemption or observed-log distribution fitting.

**실제 함수·모델:** [simulation.simulate_fifo](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

### PM-SIM-010

**업무 질문:** 설정한 크기와 operator 비율의 인공 process tree를 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.sim.generate_process_tree`

**참조 선택지:** `BASIC`, `PTANDLOGGENERATOR`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동 수·깊이·operator 비율·중복 label·seed 설정.

**검토 대상 결과:** 설정에 따라 생성한 인공 process tree.

**PIX 계산 정의:**

- Seeded binary splits from explicit labels/operator weights, max 128 leaves; sequence/xor/parallel/loop.

**남은 차이·검증 범위:**

- BASIC/PTANDLOGGENERATOR distributions and full structural/configuration options not reproduced.

**실제 함수·모델:** [simulation.generate_process_tree](../../../src/pix/case_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_simulation.py](../../../tests/case_centric/test_simulation.py)

</details>

## CC-STREAMING

**Incremental DFG, replay, rules and approximate alignment with persistent state**

### PM-STREAM-001

**업무 질문:** 도착하는 이벤트·trace를 등록한 계산기에 전달하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.stream.live_event_stream.LiveEventStream`, `pm4py.streaming.stream.live_trace_stream.LiveTraceStream`, `pm4py.streaming.algo.interface.StreamingAlgorithm`, `pm4py.streaming.util.live_to_static_stream.LiveToStaticStream`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 도착하는 이벤트/trace와 listener·수신/완료 설정.

**검토 대상 결과:** 등록 계산기로 전달되는 관측과 수신 상태 또는 누적 stream.

**PIX 계산 정의:**

- Single-writer native monitor with explicit per-case sequence/end; atomic rejects, bounded dedup/retention.

**남은 차이·검증 범위:**

- General event/trace subscriber broadcaster and async/threaded stream runtime not implemented.

**실제 함수·모델:** [streaming.CaseStream](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.close_case](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.ingest](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-003

**업무 질문:** Dataframe·OCEL 이벤트를 분석별 stream으로 나누어 공급하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.conversion.from_pandas.PandasDataframeAsIterable`, `pm4py.streaming.conversion.ocel_flatts_distributor.OcelFlattsDistributor`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Dataframe 또는 OCEL 이벤트와 객체형별 listener mapping.

**검토 대상 결과:** 순차 이벤트 또는 객체별 flat event stream.

**PIX 계산 정의:**

- CaseLog to source-order events; typed/mapping records and dataframe-like to_dict(orient="records") providers with declared sequence/source/timestamp ordering, ties, duplicates and offsets.
- OCEL explicit object-type/qualifier TraceSpec projections; one occurrence per selected object, original event/E2O qualifier provenance, selected/excluded event/object/relation counts, no cross-object causal ordering claim.
- Pure batch delivery to a new/restored native CaseStream and frozen checkpoint; failed delivery does not mutate caller monitor; explicit optional synthetic closure and capacity rejection.

**남은 차이·검증 범위:**

- This is deterministic projection and batch delivery, not a general asynchronous fan-out event bus, distributed broker transaction, backpressure system or equivalent full PM streaming runtime. Order is a selected convention and per-object projection does not become joint object-centric conformance.

**실제 함수·모델:** [stream_adapters.case_log_stream](../../../src/pix/case_centric/stream_adapters.py), [stream_adapters.consume_stream_batch](../../../src/pix/case_centric/stream_adapters.py), [stream_adapters.ocel_stream](../../../src/pix/case_centric/stream_adapters.py), [stream_adapters.records_stream](../../../src/pix/case_centric/stream_adapters.py), [stream_adapters.restore_stream_delivery](../../../src/pix/case_centric/stream_adapters.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_stream_adapters.py](../../../tests/case_centric/test_stream_adapters.py)
- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-004

**업무 질문:** 새 이벤트가 오면 DFG 빈도와 시작·끝을 갱신하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.algo.discovery.dfg.algorithm.apply`

**참조 선택지:** `FREQUENCY`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Case ID·activity가 있는 이벤트 stream과 상태 저장 설정.

**검토 대상 결과:** 갱신된 DFG·활동·시작/끝 빈도와 case별 진행 상태.

**PIX 계산 정의:**

- Online accepted-event activity/start/edge counts; end counts only on explicit close; per-case interleaving separated; aggregates survive detail eviction.

**남은 차이·검증 범위:**

- Reference finalization/stream/default policies unverified; no distributed broker/automatic watermark closure.

**실제 함수·모델:** [streaming.CaseStream.ingest](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.snapshot](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-005

**업무 질문:** Petri net token replay 상태를 이벤트마다 갱신하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.algo.conformance.tbr.algorithm.apply`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 stream·Petri net·초기/최종 marking과 replay 설정.

**검토 대상 결과:** Case별 marking과 token 기반 conformance 상태.

**PIX 계산 정의:**

- StreamingSpec replay_model: incremental marking/token counts via native silent BFS/local repair; final consumption at close; truncated silent search freezes coverage.

**남은 차이·검증 범위:**

- Replay remains local deterministic repair, not online alignment; reference repair/tie/default parity unverified.

**실제 함수·모델:** [streaming.CaseStream.close_case](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.ingest](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.snapshot](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-006

**업무 질문:** 진행 중 실행의 temporal profile 위반을 갱신하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.algo.conformance.temporal.algorithm.apply`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Timestamp 이벤트 stream·temporal profile·허용 편차 설정.

**검토 대상 결과:** Case별 temporal conformance와 위반 시간 관계.

**PIX 계산 정의:**

- StreamingSpec temporal: all earlier-source/later-target pairs under explicit inclusive second bounds, unknown/omitted denominators retained.

**남은 차이·검증 범위:**

- Automatic temporal-model learning and mean/std/zeta conversion are absent; reference pairing/default equivalence unverified.

**실제 함수·모델:** [streaming.CaseStream.ingest](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.snapshot](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-007

**업무 질문:** 진행 중 실행의 Declare automaton 상태를 갱신하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.algo.conformance.declare.algorithm.apply`

**참조 선택지:** `AUTOMATA`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 stream·Declare 규칙과 case 완료 정보.

**검토 대상 결과:** 규칙 automaton의 case별 진행·충족·위반 상태.

**PIX 계산 정의:**

- StreamingSpec declare: 22 shared templates counters/automata, pending until closure where applicable, immediate witnessed violations.

**남은 차이·검증 범위:**

- 22 native templates not a proof of all reference automata semantics; external automaton import and general Declare set unspecified.

**실제 함수·모델:** [streaming.CaseStream.close_case](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.ingest](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.snapshot](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-008

**업무 질문:** 진행 중 실행이 허용된 footprint 관계를 따르는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.algo.conformance.footprints.algorithm.apply`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 stream과 허용 footprint 관계·시작/끝 집합.

**검토 대상 결과:** 관측 경로의 footprint 적합성 상태와 위반 관계.

**PIX 계산 정의:**

- StreamingSpec footprints: activity/start/end/sequence/parallel relation checks; explicit empty policy.

**남은 차이·검증 범위:**

- Footprint abstraction does not imply full model language acceptance; source default equivalence unverified.

**실제 함수·모델:** [streaming.CaseStream.close_case](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.ingest](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.snapshot](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-009

**업무 질문:** 제한된 기억과 look-ahead로 online alignment를 근사하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.algo.conformance.alignments.algorithm.apply`

**참조 선택지:** `APPROX_IWS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 stream·모델 proxy와 look-ahead·decay·seed·탐색 한도.

**검토 대상 결과:** 제한된 proxy에 대한 온라인 근사 alignment와 비용/상태.

**PIX 계산 정의:**

- PIX proxy-trie IWS profile: finite executable accepting paths, incremental state updates, lookahead, decay, bounded beam and expansion history; no repeated batch-prefix alignment.
- Selected concrete transition-path witnesses and explicit proxy coverage/limits; open-prefix cost is not a final-alignment bound.

**남은 차이·검증 범위:**

- Reference APPROX_IWS defaults/proxy selection/approximation error not established. General optimality and model-language completeness not promised. Passing tests do not establish reference approximation-error equivalence or general optimality.

**실제 함수·모델:** [online_alignment.OnlineAlignmentStream](../../../src/pix/case_centric/online_alignment.py), [online_alignment.OnlineAlignmentStream.checkpoint](../../../src/pix/case_centric/online_alignment.py), [online_alignment.OnlineAlignmentStream.close_case](../../../src/pix/case_centric/online_alignment.py), [online_alignment.OnlineAlignmentStream.ingest](../../../src/pix/case_centric/online_alignment.py), [online_alignment.OnlineAlignmentStream.resume](../../../src/pix/case_centric/online_alignment.py), [online_alignment.OnlineAlignmentStream.snapshot](../../../src/pix/case_centric/online_alignment.py), [online_alignment.build_online_alignment_proxy](../../../src/pix/case_centric/online_alignment.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_online_alignment.py](../../../tests/case_centric/test_online_alignment.py)
- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

### PM-STREAM-010

**업무 질문:** 온라인 계산 상태를 안전하게 저장하고 재시작하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.streaming.util.dictio.generator.apply`

**참조 선택지:** `CLASSIC`, `THREAD_SAFE`, `REDIS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 상태 dictionary 요청과 메모리/thread-safe/Redis backend 설정.

**검토 대상 결과:** 온라인 계산에 쓰는 상태 저장소와 저장·조회 동작.

**PIX 계산 정의:**

- Frozen checkpoint/result persistence; request/input identity, checksum and semantic invariant validation; finite retention/Bloom membership.

**남은 차이·검증 범위:**

- THREAD_SAFE/REDIS backends and distributed durable offset transactions absent; checksums are not authentication; Bloom false rejection explicit.

**실제 함수·모델:** [streaming.CaseStream.checkpoint](../../../src/pix/case_centric/streaming.py), [streaming.CaseStream.resume](../../../src/pix/case_centric/streaming.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/case_centric/test_streaming.py](../../../tests/case_centric/test_streaming.py)

</details>

## CC-PRIVACY

**Laplace, SACOFA and PRIPEL privacy calculations**

### PM-ADV-019

**업무 질문:** 제어흐름 variant 빈도를 privacy 정의에 따라 익명화하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.privacy.anonymize_differential_privacy`

**참조 선택지:** `LAPLACE`, `SACOFA`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 로그와 privacy 예산·prefix 길이·pruning 설정.

**검토 대상 결과:** 잡음과 pruning을 적용한 제어흐름 variant 또는 합성 로그.

**PIX 계산 정의:**

- Existing privacy.anonymize_trace_variants provides Laplace/discrete-Laplace histogram profiles.
- Separate SaCoFa source: behavioral prefix scoring; harmless candidate retention; exact rational exponential harmful-subset selection; fresh count noise; class-specific pruning.
- Semantics must be public or derived from prior private release; prior/fresh budgets compose; source profile differs from pinned double-exponent selection.

**남은 차이·검증 범위:**

- Full PM SACOFA behavior/default parity and conditional privacy proof review remain pending. Public-configuration provenance is caller assertion; float count profile is not machine-DP certified. Ordinary privacy mechanism selector still rejects sacofa because this is a separate entry point.

**실제 함수·모델:** [privacy.anonymize_trace_variants](../../../src/pix/case_centric/privacy.py), [privacy.privacy_release](../../../src/pix/case_centric/privacy.py), [sacofa.anonymize_sacofa](../../../src/pix/case_centric/sacofa.py), [sacofa.sacofa_release](../../../src/pix/case_centric/sacofa.py), [sacofa.sacofa_semantics_from_release](../../../src/pix/case_centric/sacofa.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_privacy.py](../../../tests/case_centric/test_privacy.py)
- [tests/case_centric/test_sacofa.py](../../../tests/case_centric/test_sacofa.py)

</details>

### PM-ADV-020

**업무 질문:** 익명화한 제어흐름에 timestamp·속성을 privacy 정의 아래 결합하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.privacy.anonymize_differential_privacy`

**참조 선택지:** `PRIPEL`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 원본 로그·익명화한 제어흐름과 privacy 예산·속성 설정.

**검토 대상 결과:** 익명화한 timestamp·속성을 결합한 이벤트 로그.

**PIX 계산 정의:**

- Supplied control-flow query; exact injective minimum-edit-cost trace matching; occurrence-based attribute/time reconstruction; bounded numeric Laplace and categorical/boolean randomized response.
- Explicit public attribute/time domains; context budget divided across all synthetic scalar coordinates; private matching witnesses retained.

**남은 차이·검증 범위:**

- Source is a private diagnostic PRIPEL framework profile: neither envelope nor payload is an anonymized safe release. No safe-export API or machine-DP certification. Query privacy/public-domain claims and full PM theorem/default parity remain unverified.

**실제 함수·모델:** [pripel.reconstruct_pripel_context](../../../src/pix/case_centric/pripel.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/case_centric/test_pripel.py](../../../tests/case_centric/test_pripel.py)
- [tests/case_centric/test_privacy.py](../../../tests/case_centric/test_privacy.py)

</details>

---

이 문서는 현재 코드가 계산하는 정의와 남은 차이를 행별로 검토하는 자료이며, Case-Centric 참조 알고리즘의 모든 변형이 대체되었다는 판정은 아니다.
