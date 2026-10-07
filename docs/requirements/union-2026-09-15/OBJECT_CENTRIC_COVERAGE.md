# PIX Object-Centric 계산 행별 구현 범위

이 문서는 Object-Centric 검토 항목을 업무 질문별로 읽기 위한 자료다. 기준일은 2026-09-15이며,
고정한 PM4Py 2.7.23.8·OCPA 1.3.4의 대체 범위를
[실제 구현 registry](implementation_registry.json)에서 옮겼다.
전체 구조와 통합 검증 결과는 [합집합 구현 구조](../2026-09-15_PIX_NATIVE_MINING_UNION.md),
Case-Centric 항목은 [별도 문서](CASE_CENTRIC_COVERAGE.md)에서 확인할 수 있다.

한 행은 검토 단위이며, 하나의 알고리즘과 일대일로 대응하지 않는다. 행 수와 상태별 개수는 완성률이 아니다.
실제 함수의 존재, 선언된 PIX 정의의 계산, 모든 참조 variant와의 동등성을 각각 구분한다.

| 상태 | 이 문서에서의 의미 |
|---|---|
| `native_profile` | 아래 명시된 PIX 정의를 직접 계산한다. 참조의 모든 variant와의 동등성은 별도 검증 대상이다. |
| `partial` | 기능의 일부 또는 더 좁거나 다른 정의를 계산한다. 행 전체 대체 완료를 뜻하지 않는다. |
| `external_runtime_unverified` | 실행 경로는 있지만 실제 외부 runtime의 실행 근거가 충분하지 않다. |
| `unimplemented` | 대응 계산 경로가 없다. 공통 보조 함수가 있다는 이유만으로 구현으로 세지 않는다. |

Object-Centric 계산은 canonical OCEL의 event·object·E2O/O2O·qualifier와 객체 속성 이력을 다룬다.
하나의 event가 여러 object에 공동 참여하는 사실을 유지하는 계산과, 객체형별 활동열로 펼친 계산은 다르다.
Flattened replay의 평균을 joint replay나 alignment의 결과로 해석하지 않는다.

OCPN과 Object-Centric Causal Net(OCCN)은 별도 모델이다. 객체 token과 binding을 발화시키는 의미와,
marker group에 따른 인과적 의무를 실행하는 의미를 구분한다. 양방향 변환과 simulation도 각 행에서
지원되는 부분집합과 손실을 확인해야 한다. CaseLog 두 개의 interleaving으로 OCEL을 만드는 항목은
case namespace에서 시작하는 명시적 bridge이며, 유도한 연결을 원본 관측이나 인과관계로 바꾸지 않는다.

업무 질문과 검토 대상 입출력은 대체표가 요구한 범위다. 현재 PIX가 그 전체를 지원한다는 뜻은 아니다.
실제 지원은 **PIX 계산 정의**, 연결된 함수, **남은 차이·검증 범위**를 함께 읽는다.
패키지를 공유하는 행에는 공통 정의가 반복될 수 있다. 테스트 링크는 관련 코드를 찾기 위한 것으로,
그 파일의 모든 테스트가 해당 행만을 검증한다는 뜻은 아니다. 참조 symbol과 variant의 완전한 원문은
registry에 보존되어 있으며, 여기에는 대표 기능 이름만 표시한다.

근거가 유효한 범위는 registry에 고정한 소스와 명시한 입력·계산 정의다. 독립 반례, 객체 정체성이나
공동 참여의 손실, 잘못된 분모·시점·closure, 누락된 합법 binding, 저장 후 의미 변화, 참조 판본 또는
요구 정의의 변경이 확인되면 관련 판단을 수정한다. 생산 규모의 일반적인 실행 시간·메모리 한계와
Agent의 최초 수행 성공률은 **알 수 없음**이다.

## 범위와 탐색

이 문서에는 32개 구현 패키지의 100개 검토 행이 있다. 현재 상태별 행 수는 `partial` 35행, `native_profile` 65행이다. 참조 전체 대체 검증 완료를 뜻하는 행은 0행이다.

| 구현 패키지 | 다루는 범위 | 검토 행 |
|---|---|---|
| [OC-EXECUTIONS](#oc-executions) | CC/leading-object/ancestor-descendant execution profiles | 3 |
| [OC-VARIANTS](#oc-variants) | Two-phase, graph isomorphism and normalized equivalent OCEL profiles | 3 |
| [OC-EVENT-GRAPH](#oc-event-graph) | Object-event precedence graph distinct from aggregate OCDFG | 1 |
| [OC-OCDFG](#oc-ocdfg) | OCDFG with event-pair/object/total-object count profiles | 1 |
| [OC-OCPN-DISCOVERY](#oc-ocpn-discovery) | OCPN discovery profiles and diagnostic enhancement | 4 |
| [OC-SAW-DISCOVERY](#oc-saw-discovery) | Stochastic arc-weight distribution net discovery | 1 |
| [OC-OCPN-MODEL](#oc-ocpn-model) | OCPN model/binding semantics and alternative representation | 3 |
| [OC-CAUSAL-MODEL](#oc-causal-model) | Object-centric causal net marker-group semantics | 1 |
| [OC-MODEL-CONVERT](#oc-model-convert) | Direction-specific OCCN/OCPN conversion with loss report | 2 |
| [OC-MODEL-ANALYSIS](#oc-model-analysis) | OCPN subnet reachability, projection, hiding and reduction | 4 |
| [OC-ALIGNMENT](#oc-alignment) | Joint event-once object-binding alignment | 1 |
| [OC-REPLAY](#oc-replay) | Object token replay with silent/flooding policies | 2 |
| [OC-FLATTENED-REPLAY](#oc-flattened-replay) | Explicit per-type flattened replay aggregation | 1 |
| [OC-CONTEXT](#oc-context) | OCPA context fitness/precision and existing PIX binding-prefix profile | 1 |
| [OC-GRAPH-CONFORMANCE](#oc-graph-conformance) | OCDFG, ET-OT and OTG structural/frequency comparison | 2 |
| [OC-EOG-PERFORMANCE](#oc-eog-performance) | EOG input arrival and lifecycle/participation performance | 4 |
| [OC-TOKEN-PERFORMANCE](#oc-token-performance) | OPERA token-arrival performance and diagnostic annotations | 2 |
| [OC-STATISTICS](#oc-statistics) | Typed participation, object lifecycle, concurrency and cardinality statistics | 5 |
| [OC-RELATION-GRAPHS](#oc-relation-graphs) | Interaction/descendant/inheritance/co-birth/co-death, ETOT and OTG | 3 |
| [OC-INTERLEAVINGS](#oc-interleavings) | Linked-case temporal interleavings and networks | 1 |
| [OC-TRANSFORMS](#oc-transforms) | Explicit flattening, enrichment, ordering, merge and graph views | 10 |
| [OC-OLAP](#oc-olap) | OCEL drill-down/roll-up/fold/unfold | 2 |
| [OC-FILTERING](#oc-filtering) | Event/object/execution selection, closure, sampling and performance filters | 13 |
| [OC-CONSTRAINTS](#oc-constraints) | Object/activity/cardinality/control-flow/performance rule semantics | 8 |
| [OC-QUALIFIERS](#oc-qualifiers) | E2O/O2O qualifier conformance and event-time object state | 2 |
| [OC-FEATURES](#oc-features) | Object/event/execution/prefix features with named population profiles | 7 |
| [OC-FEATURE-DATASET](#oc-feature-dataset) | Feature graph, normalized split and tabular/sequential/time-series encoders | 5 |
| [OC-OCPN-SIMULATION](#oc-ocpn-simulation) | Object-centric Petri-net finite binding playout | 1 |
| [OC-OCCN-SIMULATION](#oc-occn-simulation) | Object-centric causal-net finite marker-group playout | 1 |
| [OC-ACTION-PATTERNS](#oc-action-patterns) | Temporal constraint pattern matching and action candidates | 1 |
| [OC-ACTION-SCHEDULE](#oc-action-schedule) | Action precedence/conflicts and schedule metrics | 1 |
| [OC-ACTION-IMPACT](#oc-action-impact) | Structural, marking and observed performance impact | 4 |

통합 테스트 실행 결과와 참조 수치 동등성·독립 증명은 별도 근거다. 최신 통합 실행 기록은 위의 합집합 구현 구조 문서에서 확인한다.

## OC-EXECUTIONS

**CC/leading-object/ancestor-descendant execution profiles**

### PM-OCEL-013

**업무 질문:** 서로 연결된 객체들 또는 중심 객체의 관련 실행으로 OCEL을 나눌 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.ocel.split_ocel.algorithm.apply`

**참조 선택지:** `CONNECTED_COMPONENTS`, `ANCESTORS_DESCENDANTS`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 component/ancestors-descendants 추출 설정.

**검토 대상 결과:** 분리된 실행·OCEL sublogs 및 overlap/unassigned 범위.

**PIX 계산 정의:**

- connected_components
- leading_object_nearest_type

**남은 차이·검증 범위:**

- Connected components and leading nearest-type extraction exist; equivalent_ocel additionally calculates first-participation ancestor/descendant scopes, but it is a clustering result rather than a fully equivalent general split-OCEL API.
- CC·leading-object 실행과 event order evidence가 존재한다. 일반 PM4Py split-OCEL API는 부분 대응이며, 별도 equivalent_ocel에는 first-participation ancestor/descendant 범위 계산이 있다; O2O를 실행 연결에 사용하지 않으며 orphan event/empty leading object 보존은 PIX 정의.

**실제 함수·모델:** [executions.discover_executions](../../../src/pix/compute/executions.py), [equivalent_ocel.cluster_equivalent_ocel](../../../src/pix/object_centric/equivalent_ocel.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/compute/test_executions.py](../../../tests/compute/test_executions.py)

</details>

### OC-EXEC-001

**업무 질문:** 공유 객체로 연결된 이벤트를 하나의 실행으로 묶으면 어떤 실행과 미배정 이벤트가 생기는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.process_executions.versions.connected_components.apply`, `ocpa.algo.util.process_executions.factory.apply`

**참조 선택지:** `CONN_COMP`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 분석 대상 객체형·관계 범위

**검토 대상 결과:** 연결 실행별 event/object ID, 미배정·고립 대상과 coverage

**PIX 계산 정의:**

- connected_components
- leading_object_nearest_type

**남은 차이·검증 범위:**

- E2O 연결 요소, orphan event singleton; 참조 exact parity 미검증
- CC·leading-object 실행과 event order evidence가 존재한다. 일반 PM4Py split-OCEL API는 부분 대응이며, 별도 equivalent_ocel에는 first-participation ancestor/descendant 범위 계산이 있다; O2O를 실행 연결에 사용하지 않으며 orphan event/empty leading object 보존은 PIX 정의.

**실제 함수·모델:** [executions.discover_executions](../../../src/pix/compute/executions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/compute/test_executions.py](../../../tests/compute/test_executions.py)

</details>

### OC-EXEC-002

**업무 질문:** 지정한 leading 객체를 중심으로 어떤 객체·이벤트가 실행에 포함되고 실행끼리 얼마나 겹치는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.process_executions.versions.leading_type.apply`

**참조 선택지:** `LEAD_TYPE`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, leading 객체형, 확장 규칙

**검토 대상 결과:** Leading 객체별 실행·포함 객체와 이벤트, 실행 간 overlap

**PIX 계산 정의:**

- connected_components
- leading_object_nearest_type

**남은 차이·검증 범위:**

- leading_object_nearest_type; BFS의 형별 최초 도달 깊이 규칙
- CC·leading-object 실행과 event order evidence가 존재한다. 일반 PM4Py split-OCEL API는 부분 대응이며, 별도 equivalent_ocel에는 first-participation ancestor/descendant 범위 계산이 있다; O2O를 실행 연결에 사용하지 않으며 orphan event/empty leading object 보존은 PIX 정의.

**실제 함수·모델:** [executions.discover_executions](../../../src/pix/compute/executions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/compute/test_executions.py](../../../tests/compute/test_executions.py)

</details>

## OC-VARIANTS

**Two-phase, graph isomorphism and normalized equivalent OCEL profiles**

### PM-OCEL-014

**업무 질문:** 중심 객체 실행들이 동일한 구조인지 묶어서 설명할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.cluster_equivalent_ocel`

**참조 선택지:** `VARIANT1`, `VARIANT2`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 중심 object type와 max object·rename 예외 설정.

**검토 대상 결과:** 동치 실행의 군집·설명 key 또는 PIX incidence variant.

**PIX 계산 정의:**

- event_object_incidence
- first_participation_exact_structure

**남은 차이·검증 범위:**

- Leading-object first-participation ancestor/descendant scope and exact structure canonicalization now exist. Preserves anchor/qualifier/optional O2O policies; differs from PM lexical/time renaming plus string comparison. Budget exhaustion does not return partial exact groups.
- Exact incidence variants plus first_participation_exact_structure equivalent-OCEL clustering now exist. OCPA two-phase approximation and original graph equivalence profiles remain distinct and not fully provided.

**실제 함수·모델:** [equivalent_ocel.cluster_equivalent_ocel](../../../src/pix/object_centric/equivalent_ocel.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_variants.py](../../../tests/compute/test_variants.py)
- [tests/object_centric/test_equivalent_ocel.py](../../../tests/object_centric/test_equivalent_ocel.py)

</details>

### OC-EXEC-004

**업무 질문:** 두 실행의 활동·객체 참여 graph가 같은 variant인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.variants.versions.twophase.apply`, `ocpa.algo.util.variants.factory.apply`

**참조 선택지:** `TWO_PHASE`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 실행별 EOG/객체 참여, exact 옵션·시간/상태 한도

**검토 대상 결과:** Variant 동치 집단·빈도·대표 graph와 판정 완료 범위

**PIX 계산 정의:**

- event_object_incidence
- first_participation_exact_structure

**남은 차이·검증 범위:**

- exact incidence canonicalization 존재; approximate two-phase 및 OCPA equivalence 정의 미지원
- Exact incidence variants plus first_participation_exact_structure equivalent-OCEL clustering now exist. OCPA two-phase approximation and original graph equivalence profiles remain distinct and not fully provided.

**실제 함수·모델:** [variants.discover_variants](../../../src/pix/compute/variants.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_variants.py](../../../tests/compute/test_variants.py)
- [tests/object_centric/test_equivalent_ocel.py](../../../tests/object_centric/test_equivalent_ocel.py)

</details>

### OC-EXEC-005

**업무 질문:** 전수 graph 동형 비교로 실행 variant를 분류할 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.variants.versions.onephase.apply`

**참조 선택지:** `ONE_PHASE`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 실행 graph 집합, node/edge 동치 조건·timeout

**검토 대상 결과:** 동형 관계로 나눈 variant 집단·빈도·대표 graph

**PIX 계산 정의:**

- event_object_incidence
- first_participation_exact_structure

**남은 차이·검증 범위:**

- exact graph grouping 존재하나 OCPA one-phase graph/ordering 의미 미검증
- Exact incidence variants plus first_participation_exact_structure equivalent-OCEL clustering now exist. OCPA two-phase approximation and original graph equivalence profiles remain distinct and not fully provided.

**실제 함수·모델:** [variants.discover_variants](../../../src/pix/compute/variants.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_variants.py](../../../tests/compute/test_variants.py)
- [tests/object_centric/test_equivalent_ocel.py](../../../tests/object_centric/test_equivalent_ocel.py)

</details>

## OC-EVENT-GRAPH

**Object-event precedence graph distinct from aggregate OCDFG**

### OC-EXEC-003

**업무 질문:** 객체의 이벤트 순서를 어떤 직접 후속 관계 graph로 표현하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.log.variants.util.table.eog_from_log`

**참조 선택지:** `classic`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL 또는 table/raw event 표현, 순서·qualifier 정책

**검토 대상 결과:** Event 노드와 객체별 후속 edge를 가진 EOG 및 원본 매핑

**PIX 계산 정의:**

- per_object_timestamp_order

**남은 차이·검증 범위:**

- ExecutionSet의 ProcessExecution.order_edges/order_ties가 EOG 대응 근거. 독립 discover_event_object_graph 함수는 없다. 입력 테이블 순서 대신 timestamp 및 명시 tie 정책.
- ExecutionSet의 ProcessExecution.order_edges/order_ties가 EOG 대응 근거. 독립 discover_event_object_graph 함수는 없다. 입력 테이블 순서 대신 timestamp 및 명시 tie 정책.

**실제 함수·모델:** [executions.discover_executions](../../../src/pix/compute/executions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/compute/test_executions.py](../../../tests/compute/test_executions.py)

</details>

## OC-OCDFG

**OCDFG with event-pair/object/total-object count profiles**

### PM-OCEL-005

**업무 질문:** 객체형마다 어떤 활동이 직접 이어지고 각 수치는 무엇을 세는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.discover_ocdfg`, `pm4py.statistics.ocel.edge_metrics.aggregate_ev_couples`, `pm4py.statistics.ocel.edge_metrics.aggregate_unique_objects`, `pm4py.statistics.ocel.edge_metrics.aggregate_total_objects` 외 3개(전체는 registry)

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 객체형·qualifier·순서·시간집계 설정.

**검토 대상 결과:** 객체형별 OCDFG와 활동/edge 빈도·관측 시간 근거.

**PIX 계산 정의:**

- event_pair_count
- unique_object_count
- occurrence_count

**남은 차이·검증 범위:**

- 동일 edge의 사건쌍·고유 객체·총 객체 발생 횟수를 별도 보존. qualifier 중복은 occurrence 증폭하지 않음. PM4Py의 모든 성능 annotation/parameter parity 아님.
- 동일 edge의 사건쌍·고유 객체·총 객체 발생 횟수를 별도 보존. qualifier 중복은 occurrence 증폭하지 않음. PM4Py의 모든 성능 annotation/parameter parity 아님.

**실제 함수·모델:** [ocdfg.discover_ocdfg](../../../src/pix/compute/ocdfg.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/compute/test_ocdfg.py](../../../tests/compute/test_ocdfg.py)

</details>

## OC-OCPN-DISCOVERY

**OCPN discovery profiles and diagnostic enhancement**

### PM-OCEL-006

**업무 질문:** 객체형별 net을 결합한 OCPN을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.discover_oc_petri_net`

**참조 선택지:** `WO_ANNOTATION`, `CLASSIC`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 객체형별 miner·noise·variable-arc 설정.

**검토 대상 결과:** OCPN 구조·cardinality 및 관측 수용/annotation 근거.

**PIX 계산 정의:**

- observed_range
- unique_activity
- pix.inductive_cut.v1
- pix.im.v1
- alpha
- im
- dfg
- native_joint_replay_timed_token_diagnostics

**남은 차이·검증 범위:**

- Per-type native miner and merged visible transitions with joint observed-binding witness; PM threshold double-arc/IMf/IMd/replay annotation and OCPA variable-arc determination are not all implemented. A separate native Alpha/IM/DFG per-type discovery pipeline now exists in legacy_discovery; complete reference filtering/reduction combinations remain outside the supported profiles.
- Native observed-range discovery and new per-type Alpha/IM/DFG pipeline plus enhanced replay/timing attachment exist. PM threshold double-arc, full IMf/IMd and reference filtering/variable-arc/report options remain outside these named profiles.

**실제 함수·모델:** [ocpn_discovery.discover_ocpn](../../../src/pix/compute/ocpn_discovery.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/compute/test_ocpn_discovery.py](../../../tests/compute/test_ocpn_discovery.py)
- [tests/object_centric/test_legacy_discovery.py](../../../tests/object_centric/test_legacy_discovery.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

### OC-DISC-001

**업무 질문:** 객체별 관측 흐름을 통합해 공동 참여와 variable arc를 가진 OCPN을 찾는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.discovery.ocpn.versions.new_inductive.discover_nets`, `ocpa.algo.discovery.ocpn.versions.new_inductive.discover_inductive`

**참조 선택지:** `inductive`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 객체형별 발견 및 variable arc 정책

**검토 대상 결과:** OCPN·형별 모델 매핑·관측 cardinality와 수용 근거

**PIX 계산 정의:**

- observed_range
- unique_activity
- pix.inductive_cut.v1
- pix.im.v1
- alpha
- im
- dfg
- native_joint_replay_timed_token_diagnostics

**남은 차이·검증 범위:**

- Per-type native miner and merged visible transitions with joint observed-binding witness; PM threshold double-arc/IMf/IMd/replay annotation and OCPA variable-arc determination are not all implemented. A separate native Alpha/IM/DFG per-type discovery pipeline now exists in legacy_discovery; complete reference filtering/reduction combinations remain outside the supported profiles.
- Native observed-range discovery and new per-type Alpha/IM/DFG pipeline plus enhanced replay/timing attachment exist. PM threshold double-arc, full IMf/IMd and reference filtering/variable-arc/report options remain outside these named profiles.

**실제 함수·모델:** [ocpn_discovery.discover_ocpn](../../../src/pix/compute/ocpn_discovery.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/compute/test_ocpn_discovery.py](../../../tests/compute/test_ocpn_discovery.py)
- [tests/object_centric/test_legacy_discovery.py](../../../tests/object_centric/test_legacy_discovery.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

### OC-DISC-002

**업무 질문:** 예전 OCPN 발견 경로의 Alpha·IM·DFG miner 선택은 어떤 통합 모델을 만드는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.discovery.ocpn.versions.inductive.discover_nets`, `ocpa.algo.discovery.ocpn.versions.inductive.discover_alpha`, `ocpa.algo.discovery.ocpn.versions.inductive.discover_inductive`, `ocpa.algo.discovery.ocpn.versions.inductive.discover_dfg_miner` 외 1개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 이벤트 dataframe, per-type discovery callable, 빈도 threshold

**검토 대상 결과:** 객체형별 net·object count 및 통합 OCPN

**PIX 계산 정의:**

- observed_range
- unique_activity
- pix.inductive_cut.v1
- pix.im.v1
- alpha
- im
- dfg
- native_joint_replay_timed_token_diagnostics

**남은 차이·검증 범위:**

- Per-type Classic Alpha/unfiltered native weighted IM/explicit DFG path-language discovery, visible activity merge and executable local/joint witness now exist. OCPA frequency filters, default reduction/variable-arc conventions and all backend options are not equivalent.
- Native observed-range discovery and new per-type Alpha/IM/DFG pipeline plus enhanced replay/timing attachment exist. PM threshold double-arc, full IMf/IMd and reference filtering/variable-arc/report options remain outside these named profiles.

**실제 함수·모델:** [legacy_discovery.discover_ocpn_by_type](../../../src/pix/object_centric/legacy_discovery.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/compute/test_ocpn_discovery.py](../../../tests/compute/test_ocpn_discovery.py)
- [tests/object_centric/test_legacy_discovery.py](../../../tests/object_centric/test_legacy_discovery.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

### OC-DISC-003

**업무 질문:** 발견한 OCPN에 성능 진단을 결합한 enhanced 모델을 얻는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.discovery.enhanced_ocpn.algorithm.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN, OCEL, 성능 측정·집계 옵션

**검토 대상 결과:** OCPN과 token 성능 diagnostics를 결합한 enhanced 모델

**PIX 계산 정의:**

- observed_range
- unique_activity
- pix.inductive_cut.v1
- pix.im.v1
- alpha
- im
- dfg
- native_joint_replay_timed_token_diagnostics

**남은 차이·검증 범위:**

- enhance_ocpn now joins native joint replay, timed-token samples and actual transition diagnostics; duplicate activity labels follow actual firing transition IDs. No PM/OCPA visit-matching parity.
- Native observed-range discovery and new per-type Alpha/IM/DFG pipeline plus enhanced replay/timing attachment exist. PM threshold double-arc, full IMf/IMd and reference filtering/variable-arc/report options remain outside these named profiles.

**실제 함수·모델:** [model_integration.enhance_ocpn](../../../src/pix/object_centric/model_integration.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/compute/test_ocpn_discovery.py](../../../tests/compute/test_ocpn_discovery.py)
- [tests/object_centric/test_legacy_discovery.py](../../../tests/object_centric/test_legacy_discovery.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

## OC-SAW-DISCOVERY

**Stochastic arc-weight distribution net discovery**

### PM-OCEL-025

**업무 질문:** 객체 결합의 arc-weight 분포를 가진 SAW net을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.discovery.ocel.saw_nets.algorithm.apply`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 객체형별 discovery/replay 설정.

**검토 대상 결과:** Stochastic arc-weight 분포를 갖는 SAW nets.

**PIX 계산 정의:**

- pix.observed_saw.v1

**남은 차이·검증 범위:**

- Whole-event cardinality와 concrete silent witness로 arc histogram 생성. PM4Py per-type replay/visible-event ID 집계와 다름. 확률적 firing semantics·joint distribution 곱셈은 제공하지 않음.
- Whole-event cardinality와 concrete silent witness로 arc histogram 생성. PM4Py per-type replay/visible-event ID 집계와 다름. 확률적 firing semantics·joint distribution 곱셈은 제공하지 않음.

**실제 함수·모델:** [discovery.discover_saw_net](../../../src/pix/object_centric/discovery.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_ocpn_discovery.py](../../../tests/compute/test_ocpn_discovery.py)
- [tests/object_centric/test_discovery.py](../../../tests/object_centric/test_discovery.py)

</details>

## OC-OCPN-MODEL

**OCPN model/binding semantics and alternative representation**

### PM-MODEL-026

**업무 질문:** 객체 token과 variable arc를 가진 OCPN을 구성하고 발화할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocpn.obj.OCPetriNet`, `pm4py.objects.ocpn.obj.OCMarking`, `pm4py.objects.ocpn.factory.create`, `pm4py.objects.ocpn.semantics.OCPetriNetSemantics`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Typed place·전이·variable/fixed arc·객체별 초기/최종 marking 또는 type별 net이 있는 발견 사전.

**검토 대상 결과:** 객체 ID를 유지한 OCPN과 binding의 enable·발화 후 marking.

**PIX 계산 정의:**

- finite_objects_unit_incidence
- unit_incidence_with_concrete_object_ledger

**남은 차이·검증 범위:**

- Immutable finite declared objects, unit incidence and cardinality interval. Arbitrary weighted arcs and legacy mutation/dict interfaces remain outside the native contract. Separate model_integration.decompose_ocpn/recompose_ocpn now provides ledger-assisted type-net decomposition and exact reconstruction.
- Finite declared objects/unit incidence execution and exact ledger-assisted type-net decomposition exist. Arbitrary weighted arcs and legacy mutable/dict interfaces remain outside the native model contract.

**실제 함수·모델:** [model_semantics.fire_binding](../../../src/pix/compute/model_semantics.py), [model_semantics.is_binding_enabled](../../../src/pix/compute/model_semantics.py), [model_semantics.is_object_final](../../../src/pix/compute/model_semantics.py), [object_bindings.enumerate_enabled_bindings](../../../src/pix/compute/object_bindings.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_object_bindings.py](../../../tests/compute/test_object_bindings.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

### PM-MODEL-029

**업무 질문:** OCPN을 type별 Petri net 중심의 발견 결과 표현으로 바꿀 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocpn.converter.apply`, `pm4py.objects.ocpn.variants.to_alternative_format.apply`

**참조 선택지:** `TO_ALTERNATIVE_FORMAT`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 객체 중심 Petri net과 초기/최종 객체 marking.

**검토 대상 결과:** Type별 Petri net·marking, 활동·variable arc·시작/종료 정보가 있는 대체 형식 사전.

**PIX 계산 정의:**

- finite_objects_unit_incidence
- unit_incidence_with_concrete_object_ledger

**남은 차이·검증 범위:**

- Per-type ordinary nets plus concrete-token/cardinality/shared-transition ledger now support exact OCPN recomposition. Ordinary nets alone do not preserve joint binding or variable cardinality; reference alternate dict API not promised.
- Finite declared objects/unit incidence execution and exact ledger-assisted type-net decomposition exist. Arbitrary weighted arcs and legacy mutable/dict interfaces remain outside the native model contract.

**실제 함수·모델:** [model_integration.decompose_ocpn](../../../src/pix/object_centric/model_integration.py), [model_integration.recompose_ocpn](../../../src/pix/object_centric/model_integration.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_object_bindings.py](../../../tests/compute/test_object_bindings.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

### OC-MODEL-001

**업무 질문:** OCPN place·transition·arc·marking과 변경을 표현하고 저장할 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet`, `ocpa.objects.oc_petri_net.obj.Marking`, `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet.add_arc`, `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet.remove_place` 외 8개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Place/transition/arc/marking과 ID, 명시 변경

**검토 대상 결과:** OCPN 구조·marking·조회 결과·직렬화 표현

**PIX 계산 정의:**

- finite_objects_unit_incidence
- unit_incidence_with_concrete_object_ledger

**남은 차이·검증 범위:**

- Immutable finite declared objects, unit incidence and cardinality interval. Arbitrary weighted arcs and legacy mutation/dict interfaces remain outside the native contract. Separate model_integration.decompose_ocpn/recompose_ocpn now provides ledger-assisted type-net decomposition and exact reconstruction.
- Finite declared objects/unit incidence execution and exact ledger-assisted type-net decomposition exist. Arbitrary weighted arcs and legacy mutable/dict interfaces remain outside the native model contract.

**실제 함수·모델:** [model_semantics.fire_binding](../../../src/pix/compute/model_semantics.py), [model_semantics.is_binding_enabled](../../../src/pix/compute/model_semantics.py), [model_semantics.is_object_final](../../../src/pix/compute/model_semantics.py), [object_bindings.enumerate_enabled_bindings](../../../src/pix/compute/object_bindings.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_object_bindings.py](../../../tests/compute/test_object_bindings.py)
- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)

</details>

## OC-CAUSAL-MODEL

**Object-centric causal net marker-group semantics**

### PM-MODEL-025

**업무 질문:** 입출력 marker group·cardinality로 객체 중심 causal net을 만들고 상태를 해석할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.oc_causal_net.obj.OCCausalNet`, `pm4py.objects.oc_causal_net.creation.factory.create_oc_causal_net`, `pm4py.objects.oc_causal_net.semantics.OCCausalNetState`, `pm4py.objects.oc_causal_net.semantics.OCCausalNetSemantics`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동별 입출력 marker group·객체 유형·최소/최대 참여 수·공유 marker key와 의무 상태.

**검토 대상 결과:** OCCausalNet 모델과 outstanding obligation의 소비·생성에 따른 실행 상태.

**PIX 계산 정의:**

- pix.finite_object_obligation_net.v1

**남은 차이·검증 범위:**

- 유한 concrete-object obligation channel, OR marker-group/AND marker, equality/disjointness. PM4Py marker semantics·START_/END_ convention 전체 동등성 아님.
- 유한 concrete-object obligation channel, OR marker-group/AND marker, equality/disjointness. PM4Py marker semantics·START_/END_ convention 전체 동등성 아님.

**실제 함수·모델:** [models.causal_net_digest](../../../src/pix/object_centric/models.py), [models.enumerate_enabled_causal_bindings](../../../src/pix/object_centric/models.py), [models.fire_causal_binding](../../../src/pix/object_centric/models.py), [models.is_causal_binding_enabled](../../../src/pix/object_centric/models.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

## OC-MODEL-CONVERT

**Direction-specific OCCN/OCPN conversion with loss report**

### PM-MODEL-027

**업무 질문:** OCCausalNet을 OCPN으로 변환하면 어떤 제약이 유지되거나 손실되는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.oc_causal_net.converter.apply`, `pm4py.objects.oc_causal_net.variants.to_ocpn.apply`

**참조 선택지:** `TO_OCPN`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 입출력 marker group·key·참여 수 범위가 있는 OCCausalNet.

**검토 대상 결과:** Marker 구조를 Petri net으로 옮긴 OCPN과 cardinality/key/marking 손실 정보.

**PIX 계산 정의:**

- finite_object_obligation_conversion

**남은 차이·검증 범위:**

- causal_net_to_ocpn only representable shared-object groups; independent/disjoint same-type channels rejected, alternatives duplicate transitions under an explicit limit.
- 방향별 명시적 변환과 불가 사유 존재. 지원하지 않는 causal disjoint-channel 조건 및 임의 PM4Py 모델 변환은 성공으로 위장하지 않음.

**실제 함수·모델:** [models.causal_net_to_ocpn](../../../src/pix/object_centric/models.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

### PM-MODEL-028

**업무 질문:** OCPN의 객체 흐름을 marker 기반 causal net으로 표현할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocpn.converter.apply`, `pm4py.objects.ocpn.variants.to_oc_causal_net.apply`

**참조 선택지:** `TO_OC_CAUSAL_NET`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Object-centric Petri net의 typed place·arc·전이와 초기/최종 marking.

**검토 대상 결과:** Auxiliary 활동·type별 START/END·입출력 marker group을 가진 OCCausalNet.

**PIX 계산 정의:**

- finite_object_obligation_conversion

**남은 차이·검증 범위:**

- ocpn_to_causal_net only channel nets with at most one producer and consumer per place; shared-choice places rejected. General OCPN conversion missing.
- 방향별 명시적 변환과 불가 사유 존재. 지원하지 않는 causal disjoint-channel 조건 및 임의 PM4Py 모델 변환은 성공으로 위장하지 않음.

**실제 함수·모델:** [models.ocpn_to_causal_net](../../../src/pix/object_centric/models.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

## OC-MODEL-ANALYSIS

**OCPN subnet reachability, projection, hiding and reduction**

### OC-MODEL-002

**업무 질문:** 객체형별로 특정 활동의 선행·후행 노드와 두 활동 사이 subnet을 구할 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet.ancestor_transitions`, `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet.ancestor_places`, `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet.descendant_transitions`, `ocpa.objects.oc_petri_net.obj.ObjectCentricPetriNet.descendant_places` 외 1개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN, 객체형, 기준 활동 또는 source/target

**검토 대상 결과:** Ancestor/descendant place·transition 집합 또는 subnet

**PIX 계산 정의:**

- ancestors
- descendants
- parallel_places
- parallel_transitions
- silent_self_loop
- series_places
- explicit_transition_ids
- all_transitions_with_selected_activity_labels
- all_transitions_incident_to_selected_types

**남은 차이·검증 범위:**

- Global original-ID ancestor/descendant traversal; OCPA local object-type-net/source-target subnet semantics not fully present.
- Projection/hiding/subnet/four conservative reductions plus dedicated subprocess participation predicate exist. OCPA six-rule Murata coverage and local source-target subnet semantics remain partial; finite reachability soundness stays a separate extension.

**실제 함수·모델:** [models.object_subnet](../../../src/pix/object_centric/models.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)
- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

### OC-MODEL-003

**업무 질문:** 객체형·subprocess로 OCPN을 투영하거나 일부 활동을 숨길 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.ocpn_analysis.projection.versions.project_on_subprocess.old_apply`

**참조 선택지:** `object_types`, `subprocess`, `hiding`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN, 객체형/구간/숨길 활동 선택

**검토 대상 결과:** 투영 또는 숨김 처리 모델과 원본 요소 매핑·손실/보존 설명

**PIX 계산 정의:**

- ancestors
- descendants
- parallel_places
- parallel_transitions
- silent_self_loop
- series_places
- explicit_transition_ids
- all_transitions_with_selected_activity_labels
- all_transitions_incident_to_selected_types

**남은 차이·검증 범위:**

- Structural projection and silent-label hiding exist; source-target subprocess and post-hiding reduction combination not provided.
- Projection/hiding/subnet/four conservative reductions plus dedicated subprocess participation predicate exist. OCPA six-rule Murata coverage and local source-target subnet semantics remain partial; finite reachability soundness stays a separate extension.

**실제 함수·모델:** [models.hide_ocpn](../../../src/pix/object_centric/models.py), [models.project_ocpn](../../../src/pix/object_centric/models.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)
- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

### OC-MODEL-004

**업무 질문:** 보존 조건 아래 OCPN의 불필요한 place·transition을 줄일 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.ocpn_analysis.reduction.versions.murata.FST`, `ocpa.algo.enhancement.ocpn_analysis.reduction.versions.murata.FSP`, `ocpa.algo.enhancement.ocpn_analysis.reduction.versions.murata.FPT`, `ocpa.algo.enhancement.ocpn_analysis.reduction.versions.murata.FPP` 외 2개(전체는 registry)

**참조 선택지:** `murata`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN, 보존할 visible·초기/최종 노드

**검토 대상 결과:** 축약 OCPN, 적용 rule 및 보존 조건

**PIX 계산 정의:**

- ancestors
- descendants
- parallel_places
- parallel_transitions
- silent_self_loop
- series_places
- explicit_transition_ids
- all_transitions_with_selected_activity_labels
- all_transitions_incident_to_selected_types

**남은 차이·검증 범위:**

- Four conservative reductions: parallel places, parallel transitions, silent self-loop, series places; not all six OCPA Murata rules.
- Projection/hiding/subnet/four conservative reductions plus dedicated subprocess participation predicate exist. OCPA six-rule Murata coverage and local source-target subnet semantics remain partial; finite reachability soundness stays a separate extension.

**실제 함수·모델:** [models.reduce_ocpn](../../../src/pix/object_centric/models.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)
- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

### OC-MODEL-005

**업무 질문:** 선택 활동과 객체형이 subprocess의 참여 조건을 만족하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.oc_petri_net.obj.Subprocess`, `ocpa.objects.oc_petri_net.obj.Subprocess.sound`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN, 선택 활동·객체형

**검토 대상 결과:** Subprocess와 제한된 incidence 충족 여부

**PIX 계산 정의:**

- ancestors
- descendants
- parallel_places
- parallel_transitions
- silent_self_loop
- series_places
- explicit_transition_ids
- all_transitions_with_selected_activity_labels
- all_transitions_incident_to_selected_types

**남은 차이·검증 범위:**

- Exact existential incidence predicate now exists: every selected transition needs at least one incident place of any selected type, not every type. Explicit same-label transitions all checked; empty selection marked vacuous; soundness_established remains None.
- Projection/hiding/subnet/four conservative reductions plus dedicated subprocess participation predicate exist. OCPA six-rule Murata coverage and local source-target subnet semantics remain partial; finite reachability soundness stays a separate extension.

**실제 함수·모델:** [model_integration.check_subprocess_participation](../../../src/pix/object_centric/model_integration.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)
- [tests/object_centric/test_models.py](../../../tests/object_centric/test_models.py)

</details>

## OC-ALIGNMENT

**Joint event-once object-binding alignment**

### OC-CONF-001

**업무 질문:** 실행의 이벤트·객체 참여를 OCPN과 맞추는 최소 비용 joint alignment는 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.alignments.algorithm.calculate_oc_alignments`, `ocpa.algo.conformance.alignments.algorithm.calculate_oc_alignment_given_variant_id`, `ocpa.algo.conformance.alignments.algorithm.dijkstra`, `ocpa.algo.conformance.alignments.algorithm.get_all_event_objects` 외 15개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL execution/variant, OCPN, 비용·객체/순서 범위

**검토 대상 결과:** Joint move sequence·binding·최종 marking·비용과 완료/한도

**PIX 계산 정의:**

- whole_log
- event_cost
- object_cost

**남은 차이·검증 범위:**

- 동일 event 한 번 소비하는 joint Dijkstra; finite concrete IDs, exact final marking, event/object 비용. OCPA execution/variant 단위·마킹 생성·정규화 적합성과 같다는 주장 없음.
- 동일 event 한 번 소비하는 joint Dijkstra; finite concrete IDs, exact final marking, event/object 비용. OCPA execution/variant 단위·마킹 생성·정규화 적합성과 같다는 주장 없음.

**실제 함수·모델:** [object_conformance.align_object_log](../../../src/pix/compute/object_conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/compute/test_object_conformance.py](../../../tests/compute/test_object_conformance.py)

</details>

## OC-REPLAY

**Object token replay with silent/flooding policies**

### OC-CONF-002

**업무 질문:** 공동 객체 흐름의 missing/remaining/consumed/produced token과 fitness는 얼마인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.token_based_replay.algorithm.apply`, `ocpa.algo.conformance.token_based_replay.variants.object_centric_replay.apply`

**참조 선택지:** `object_centric`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, OCPN, silent/flooding/replay 설정

**검토 대상 결과:** 객체 token p/c/m/r, fitness, 객체·place별 보정 진단

**PIX 계산 정의:**

- joint_lexical_topological_silent_bfs_local_repair_v1

**남은 차이·검증 범위:**

- joint replay 자체 존재, 최적 수선 아님
- Native forward silent BFS·deterministic local repair. Token conservation p+m=c+r, capped search unknown. OCPA backwards BST/cache/shortest path/flooding freezing 없음.

**실제 함수·모델:** [conformance.replay_object_log](../../../src/pix/object_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_conformance.py](../../../tests/object_centric/test_conformance.py)

</details>

### OC-CONF-005

**업무 질문:** Silent transition 경로와 token flooding을 replay에서 어떤 정책으로 다루는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.token_based_replay.backward_replay.algorithm.bst_backward_replay`, `ocpa.algo.conformance.token_based_replay.backward_replay.algorithm.cashed_bst_backward_replay`, `ocpa.algo.conformance.token_based_replay.backward_replay.algorithm.shortest_path_backward_replay`, `ocpa.algo.conformance.token_based_replay.enhancement.address_token_flooding.solve_token_flooding` 외 3개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Marking, 대상 객체/transition, silent graph와 cache

**검토 대상 결과:** Silent 경로·변경 marking·token 보정과 탐색 종료 상태

**PIX 계산 정의:**

- joint_lexical_topological_silent_bfs_local_repair_v1

**남은 차이·검증 범위:**

- forward silent BFS만 제공; backwards search/BST cache/flooding·freezing 전략 미구현
- Native forward silent BFS·deterministic local repair. Token conservation p+m=c+r, capped search unknown. OCPA backwards BST/cache/shortest path/flooding freezing 없음.

**실제 함수·모델:** [conformance.replay_object_log](../../../src/pix/object_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_conformance.py](../../../tests/object_centric/test_conformance.py)

</details>

## OC-FLATTENED-REPLAY

**Explicit per-type flattened replay aggregation**

### OC-CONF-003

**업무 질문:** 객체형별로 평탄화한 replay 점수를 합산하면 어떤 fitness가 나오는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.token_based_replay.variants.flattened_replay.apply`

**참조 선택지:** `flattened`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, OCPN의 객체형 projection, replay 설정

**검토 대상 결과:** Flattened replay 합계 p/c/m/r와 정규화 fitness

**PIX 계산 정의:**

- per_concrete_object_projection_token_weighted_v1

**남은 차이·검증 범위:**

- Concrete object별 projected replay와 p/c/m/r 합산 fitness. Shared event 반복 계수·동기화 소실 명시. 참조 경로 선택·isolate·zero denominator와 다를 수 있음.
- Concrete object별 projected replay와 p/c/m/r 합산 fitness. Shared event 반복 계수·동기화 소실 명시. 참조 경로 선택·isolate·zero denominator와 다를 수 있음.

**실제 함수·모델:** [conformance.replay_flattened_object_log](../../../src/pix/object_centric/conformance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_conformance.py](../../../tests/object_centric/test_conformance.py)

</details>

## OC-CONTEXT

**OCPA context fitness/precision and existing PIX binding-prefix profile**

### OC-CONF-004

**업무 질문:** 객체별 과거 context에서 로그와 모델의 가능한 다음 활동이 얼마나 일치하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.precision_and_fitness.utils.calculate_contexts_and_bindings`, `ocpa.algo.conformance.precision_and_fitness.variants.replay_context.enabled_log_activities`, `ocpa.algo.conformance.precision_and_fitness.variants.replay_context.enabled_model_activities_multiprocessing`, `ocpa.algo.conformance.precision_and_fitness.variants.replay_context.calculate_precision_and_fitness`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, OCPN, 선택적 사전 계산 context/binding

**검토 대상 결과:** Context precision·fitness와 평가/제외 모집단

**PIX 계산 정의:**

- pix.object_context.binding_prefix.v1
- micro_behavior_sets
- termination_excluded

**남은 차이·검증 범위:**

- PIX concrete binding-prefix context 존재. OCPA context fitness/precision의 집계·participant/termination 정의와 동일하지 않으며 OCPA profile 선택자는 없음.
- PIX concrete binding-prefix context 존재. OCPA context fitness/precision의 집계·participant/termination 정의와 동일하지 않으며 OCPA profile 선택자는 없음.

**실제 함수·모델:** [object_context.measure_object_context](../../../src/pix/compute/object_context.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/compute/test_object_context.py](../../../tests/compute/test_object_context.py)
- [tests/compute/test_object_context_oracle.py](../../../tests/compute/test_object_context_oracle.py)

</details>

## OC-GRAPH-CONFORMANCE

**OCDFG, ET-OT and OTG structural/frequency comparison**

### PM-OCEL-023

**업무 질문:** 실제 OCDFG와 기준 OCDFG의 활동·경로·빈도 차이는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_ocdfg`

**참조 선택지:** `GRAPH_COMPARISON`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 관측 OCEL/OCDFG와 기준 OCDFG, 차이 threshold·가중치.

**검토 대상 결과:** 활동/flow 누락·추가·빈도 차이와 graph conformance 지표.

**PIX 계산 정의:**

- edge_coverage_support_jaccard
- frequency_min_overlap_l1
- typed_symmetric
- reference_untyped

**남은 차이·검증 범위:**

- OCDFG weighted structure and strict absolute-threshold comparison implemented with reference_untyped/typed_symmetric profiles, exact score fractions, raw-source versus participating graph population and explicit zero-domain convention. Tests and independent oracle source exist; final integrated execution evidence is recorded separately, with no upstream execution parity established.
- OCDFG weighted structural/threshold formulas now implemented separately from generic Object/ETOT/OTG graph comparisons. Reference ETOT/OTG composite relative-frequency conformance remains partial.

**실제 함수·모델:** [graph_comparison.compare_ocdfgs](../../../src/pix/object_centric/graph_comparison.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_graph_comparison.py](../../../tests/object_centric/test_graph_comparison.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

### PM-OCEL-024

**업무 질문:** 실제 ET-OT·OTG와 기준 graph의 관계·빈도 차이는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.conformance.conformance_otg`, `pm4py.conformance.conformance_etot`

**참조 선택지:** `GRAPH_COMPARISON`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 관측 OCEL/ET-OT/OTG와 기준 graph, threshold·가중치.

**검토 대상 결과:** 관계·노드·빈도 차이 및 graph-comparison 점수.

**PIX 계산 정의:**

- edge_coverage_support_jaccard
- frequency_min_overlap_l1
- typed_symmetric
- reference_untyped

**남은 차이·검증 범위:**

- Object/ETOT/OTG edge and frequency Jaccard/coverage/l1 are implemented. Pinned ETOT/OTG composite relative-frequency fitness/threshold/node formulas remain absent.
- OCDFG weighted structural/threshold formulas now implemented separately from generic Object/ETOT/OTG graph comparisons. Reference ETOT/OTG composite relative-frequency conformance remains partial.

**실제 함수·모델:** [relations.compare_object_graphs](../../../src/pix/object_centric/relations.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_graph_comparison.py](../../../tests/object_centric/test_graph_comparison.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

## OC-EOG-PERFORMANCE

**EOG input arrival and lifecycle/participation performance**

### OC-PERF-001

**업무 질문:** 이벤트의 선행 입력 도착 차이로 flow·sojourn·synchronization·pooling·lagging·readiness를 계산하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.flow_time`, `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.sojourn_time`, `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.synchronization_time`, `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.pooling_time` 외 2개(전체는 registry)

**참조 선택지:** `event_object_graph_based`, `flow`, `sojourn`, `synchronization`, `pooling`, `lagging`, `rediness`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL EOG, 활동·객체형, 측정·집계 선택

**검토 대상 결과:** flow/sojourn/synchronization/pooling/lagging/readiness 표본·집계

**PIX 계산 정의:**

- object_predecessor
- ocpa_eog_1_3_4

**남은 차이·검증 범위:**

- EOG arrival timing metrics implemented with object_predecessor and ocpa_eog_1_3_4 profile distinctions.
- EOG 10 source function 대응 산술과 시간/빈도 samples 존재. explicit EOG profile은 typed event attribution/boundary zero 보존하지만 row-order·defect까지 재현하지 않음. std/median 등 집계 목록 미완.

**실제 함수·모델:** [performance.measure_performance](../../../src/pix/object_centric/performance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_performance.py](../../../tests/object_centric/test_performance.py)

</details>

### OC-PERF-002

**업무 질문:** EOG에서 특정 활동의 elapsed/remaining 시간이 어떤 구간을 뜻하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.elapsed_time`, `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.remaining_time`

**참조 선택지:** `elapsed`, `remaining`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL EOG, 활동·객체형·집계

**검토 대상 결과:** 참조의 인접 선행/후속 기준 elapsed/remaining 표본·집계

**PIX 계산 정의:**

- object_predecessor
- ocpa_eog_1_3_4

**남은 차이·검증 범위:**

- Lifecycle vs immediate-neighbor elapsed/remaining explicitly separate.
- EOG 10 source function 대응 산술과 시간/빈도 samples 존재. explicit EOG profile은 typed event attribution/boundary zero 보존하지만 row-order·defect까지 재현하지 않음. std/median 등 집계 목록 미완.

**실제 함수·모델:** [performance.measure_performance](../../../src/pix/object_centric/performance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_performance.py](../../../tests/object_centric/test_performance.py)

</details>

### OC-PERF-003

**업무 질문:** 활동에 참여한 객체 수와 객체별 활동 발생 수의 분포는 얼마인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.object_freq`, `ocpa.algo.enhancement.event_graph_based_performance.versions.event_object_graph_based.act_freq`

**참조 선택지:** `object_freq`, `act_freq`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 활동·객체형·집계

**검토 대상 결과:** Event별 객체 수 또는 객체별 활동 수 분포와 요약값

**PIX 계산 정의:**

- object_predecessor
- ocpa_eog_1_3_4

**남은 차이·검증 범위:**

- Distinct-object event frequency and activity event counts per object implemented.
- EOG 10 source function 대응 산술과 시간/빈도 samples 존재. explicit EOG profile은 typed event attribution/boundary zero 보존하지만 row-order·defect까지 재현하지 않음. std/median 등 집계 목록 미완.

**실제 함수·모델:** [performance.measure_performance](../../../src/pix/object_centric/performance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_performance.py](../../../tests/object_centric/test_performance.py)

</details>

### OC-PERF-006

**업무 질문:** 성능 표본을 평균·중앙값·표준편차·합·최소·최대로 요약하면 어떤 값인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.aggregate_stats`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.aggregate_ot_stats`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.aggregate_perf_records`

**참조 선택지:** `avg`, `med`, `std`, `sum`, `min`, `max`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 활동/객체형별 수치 표본, 집계 종류

**검토 대상 결과:** Mean/median/stdev/sum/min/max, 모집단 크기·결측 근거

**PIX 계산 정의:**

- object_predecessor
- ocpa_eog_1_3_4

**남은 차이·검증 범위:**

- total/min/max/exact mean만 존재; std/median 등 참조 aggregation 전부 아님
- EOG 10 source function 대응 산술과 시간/빈도 samples 존재. explicit EOG profile은 typed event attribution/boundary zero 보존하지만 row-order·defect까지 재현하지 않음. std/median 등 집계 목록 미완.

**실제 함수·모델:** [performance.measure_performance](../../../src/pix/object_centric/performance.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_performance.py](../../../tests/object_centric/test_performance.py)

</details>

## OC-TOKEN-PERFORMANCE

**OPERA token-arrival performance and diagnostic annotations**

### OC-PERF-004

**업무 질문:** Replay token 도착과 실제 시작·완료를 연결한 OPERA 성능은 얼마인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.PerformanceAnalysis.analyze`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.PerformanceAnalysis.measure_waiting`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.PerformanceAnalysis.measure_service`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.PerformanceAnalysis.measure_sojourn` 외 3개(전체는 registry)

**참조 선택지:** `opera`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN, OCEL의 start/complete, token replay·집계 설정

**검토 대상 결과:** TokenVisit에 연결된 시간 표본과 활동/객체형 성능 diagnostics

**PIX 계산 정의:**

- token_arrivals
- ocpa_opera_1_3_4
- fifo_production
- zero_duration_max_input
- native_joint_replay_timed_token_diagnostics

**남은 차이·검증 범위:**

- timed replay samples 존재; 원본 replay visit matching parity 아님
- Timed-token ledger and enhanced transition diagnostics exist. Initial/injected unknown clocks and native visit matching are explicit; complete OPERA frequency/aggregation report and measured silent timing remain missing.

**실제 함수·모델:** [performance.measure_replay_performance](../../../src/pix/object_centric/performance.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)
- [tests/object_centric/test_performance.py](../../../tests/object_centric/test_performance.py)

</details>

### OC-PERF-005

**업무 질문:** 모델 activity·arc 빈도와 객체 참여/fitness 진단을 어떻게 집계·annotation하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.aggregate_frequencies`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.transform_diagnostics`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.merge_replay`, `ocpa.algo.enhancement.token_replay_based_performance.versions.opera.merge_place_fitness` 외 4개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Replay diagnostics, 모델 매핑, 집계 선택

**검토 대상 결과:** Activity/arc 빈도·object count·place fitness annotation

**PIX 계산 정의:**

- token_arrivals
- ocpa_opera_1_3_4
- fifo_production
- zero_duration_max_input
- native_joint_replay_timed_token_diagnostics

**남은 차이·검증 범위:**

- Enhanced OCPN now attaches transition event/token counts and timing samples to actual replay transitions. The complete OPERA activity/object/arc frequency and optional aggregation report remains not fully reproduced.
- Timed-token ledger and enhanced transition diagnostics exist. Initial/injected unknown clocks and native visit matching are explicit; complete OPERA frequency/aggregation report and measured silent timing remain missing.

**실제 함수·모델:** [model_integration.enhance_ocpn](../../../src/pix/object_centric/model_integration.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_model_integration.py](../../../tests/object_centric/test_model_integration.py)
- [tests/object_centric/test_performance.py](../../../tests/object_centric/test_performance.py)

</details>

## OC-STATISTICS

**Typed participation, object lifecycle, concurrency and cardinality statistics**

### PM-OCEL-001

**업무 질문:** 객체형·속성 목록과 활동별 객체 참여 개수는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_get_object_types`, `pm4py.ocel.ocel_get_attribute_names`, `pm4py.ocel.ocel_object_type_activities`, `pm4py.ocel.ocel_objects_ot_count`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL 타입 정의·속성과 E2O 관계.

**검토 대상 결과:** 객체형·속성 목록, 활동×객체형 참여 및 event cardinality.

**PIX 계산 정의:**

- unique_qualified_event_object_participation
- median_gt_one
- any_gt_one
- all_selected_events
- selected_participating_events

**남은 차이·검증 범위:**

- 형·활동 참여 계산 있음; attribute names facade와 raw relation counting parity 없음
- Participation/lifecycle/cardinality/convergence and exact timestamp temporal summaries now exist; event counts and relation multiplicity remain separate. Broad convenience attribute-name and full source summary outputs remain partial.

**실제 함수·모델:** [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [relations.discover_object_graph](../../../src/pix/object_centric/relations.py), [statistics.object_statistics](../../../src/pix/object_centric/statistics.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)
- [tests/object_centric/test_statistics.py](../../../tests/object_centric/test_statistics.py)
- [tests/object_centric/test_temporal_summary.py](../../../tests/object_centric/test_temporal_summary.py)

</details>

### PM-OCEL-002

**업무 질문:** 동일 시각에 일어난 활동과 참여 객체들은 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_temporal_summary`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL E2O와 event timestamp.

**검토 대상 결과:** 시각별 활동·객체 목록과 unique/occurrence 단위.

**PIX 계산 정의:**

- unique_qualified_event_object_participation
- median_gt_one
- any_gt_one
- all_selected_events
- selected_participating_events

**남은 차이·검증 범위:**

- Exact UTC timestamp buckets now preserve distinct event/activity/object/participation and qualified-relation counts. Relation-only population explicit; default includes relation-less events. Does not infer order or reproduce arbitrary list order.
- Participation/lifecycle/cardinality/convergence and exact timestamp temporal summaries now exist; event counts and relation multiplicity remain separate. Broad convenience attribute-name and full source summary outputs remain partial.

**실제 함수·모델:** [temporal_summary.temporal_summary](../../../src/pix/object_centric/temporal_summary.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)
- [tests/object_centric/test_statistics.py](../../../tests/object_centric/test_statistics.py)
- [tests/object_centric/test_temporal_summary.py](../../../tests/object_centric/test_temporal_summary.py)

</details>

### PM-OCEL-003

**업무 질문:** 객체별 관측 활동열·기간·상호작용 객체는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_objects_summary`, `pm4py.ocel.ocel_objects_interactions_summary`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL 객체별 event 참여와 timestamp.

**검토 대상 결과:** 객체별 활동열·관측 span 및 event별 상호작용 pair.

**PIX 계산 정의:**

- unique_qualified_event_object_participation
- median_gt_one
- any_gt_one
- all_selected_events
- selected_participating_events

**남은 차이·검증 범위:**

- lifecycle/interaction primitives 있음; 참조 전체 summary output 아님
- Participation/lifecycle/cardinality/convergence and exact timestamp temporal summaries now exist; event counts and relation multiplicity remain separate. Broad convenience attribute-name and full source summary outputs remain partial.

**실제 함수·모델:** [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [relations.discover_object_graph](../../../src/pix/object_centric/relations.py), [statistics.object_statistics](../../../src/pix/object_centric/statistics.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)
- [tests/object_centric/test_statistics.py](../../../tests/object_centric/test_statistics.py)
- [tests/object_centric/test_temporal_summary.py](../../../tests/object_centric/test_temporal_summary.py)

</details>

### PM-OCEL-033

**업무 질문:** OCEL의 관계 multiplicity 때문에 flattening에 convergence/divergence가 생기는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocel.util.convergence_divergence_diagnostics.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL E2O의 활동×객체형 참여 multiplicity.

**검토 대상 결과:** Convergence/divergence 진단과 원인 관계 집합.

**PIX 계산 정의:**

- unique_qualified_event_object_participation
- median_gt_one
- any_gt_one
- all_selected_events
- selected_participating_events

**남은 차이·검증 범위:**

- unique participation median>1 및 ANY witness 분리
- Participation/lifecycle/cardinality/convergence and exact timestamp temporal summaries now exist; event counts and relation multiplicity remain separate. Broad convenience attribute-name and full source summary outputs remain partial.

**실제 함수·모델:** [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [relations.discover_object_graph](../../../src/pix/object_centric/relations.py), [statistics.object_statistics](../../../src/pix/object_centric/statistics.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)
- [tests/object_centric/test_statistics.py](../../../tests/object_centric/test_statistics.py)
- [tests/object_centric/test_temporal_summary.py](../../../tests/object_centric/test_temporal_summary.py)

</details>

### OC-DATA-004

**업무 질문:** 이벤트-객체 조회와 특정 활동을 포함하거나 잇는 객체 수를 계산하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.log.variants.obj.ObjectCentricEventLog.eve_ot_objects`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.ot_objects_of_an_event`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.num_ot_objects_containing_acts`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.num_ot_objects_containing_act1_followed_by_act2` 외 3개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL index, event/activity/object type 질의

**검토 대상 결과:** 관련 객체 ID 및 조건별 객체/event count

**PIX 계산 정의:**

- unique_qualified_event_object_participation
- median_gt_one
- any_gt_one
- all_selected_events
- selected_participating_events

**남은 차이·검증 범위:**

- object_statistics + measure_rule_metric로 참여·활동 관계 산술 구성 가능
- Participation/lifecycle/cardinality/convergence and exact timestamp temporal summaries now exist; event counts and relation multiplicity remain separate. Broad convenience attribute-name and full source summary outputs remain partial.

**실제 함수·모델:** [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [relations.discover_object_graph](../../../src/pix/object_centric/relations.py), [statistics.object_statistics](../../../src/pix/object_centric/statistics.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)
- [tests/object_centric/test_statistics.py](../../../tests/object_centric/test_statistics.py)
- [tests/object_centric/test_temporal_summary.py](../../../tests/object_centric/test_temporal_summary.py)

</details>

## OC-RELATION-GRAPHS

**Interaction/descendant/inheritance/co-birth/co-death, ETOT and OTG**

### PM-OCEL-007

**업무 질문:** 공동 참여·후속·계승·동시 최초/최종 관측 관계를 graph로 만들 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.discover_objects_graph`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL event–object 참여와 선택 graph_type.

**검토 대상 결과:** Interaction/descendant/inheritance/cobirth/codeath 객체 edge 집합.

**PIX 계산 정의:**

- interaction
- descendants
- inheritance
- cobirth
- codeath
- qualified_relations
- event_object_pairs
- events
- objects
- type_id
- object_id

**남은 차이·검증 범위:**

- 5종 graph/ETOT/OTG 실계산. timestamp ordering/tie 선택·qualifier·isolate 보존 명시. ETOT frequency populations·OTG undirected orientation 분리; runtime parity 아님.
- 5종 graph/ETOT/OTG 실계산. timestamp ordering/tie 선택·qualifier·isolate 보존 명시. ETOT frequency populations·OTG undirected orientation 분리; runtime parity 아님.

**실제 함수·모델:** [relations.discover_object_graph](../../../src/pix/object_centric/relations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

### PM-OCEL-021

**업무 질문:** 활동형–객체형 참여 graph와 빈도는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_etot`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL의 활동형·객체형과 E2O 관계행.

**검토 대상 결과:** ET-OT bipartite graph와 참여 edge frequency.

**PIX 계산 정의:**

- interaction
- descendants
- inheritance
- cobirth
- codeath
- qualified_relations
- event_object_pairs
- events
- objects
- type_id
- object_id

**남은 차이·검증 범위:**

- 5종 graph/ETOT/OTG 실계산. timestamp ordering/tie 선택·qualifier·isolate 보존 명시. ETOT frequency populations·OTG undirected orientation 분리; runtime parity 아님.
- 5종 graph/ETOT/OTG 실계산. timestamp ordering/tie 선택·qualifier·isolate 보존 명시. ETOT frequency populations·OTG undirected orientation 분리; runtime parity 아님.

**실제 함수·모델:** [relations.discover_etot](../../../src/pix/object_centric/relations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

### PM-OCEL-022

**업무 질문:** 객체 관계를 객체형 수준으로 묶은 OTG는 무엇인가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.discovery.discover_otg`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 유도 객체 graph 다섯 종류.

**검토 대상 결과:** 관계별 object-type graph와 type-pair edge frequency.

**PIX 계산 정의:**

- interaction
- descendants
- inheritance
- cobirth
- codeath
- qualified_relations
- event_object_pairs
- events
- objects
- type_id
- object_id

**남은 차이·검증 범위:**

- 5종 graph/ETOT/OTG 실계산. timestamp ordering/tie 선택·qualifier·isolate 보존 명시. ETOT frequency populations·OTG undirected orientation 분리; runtime parity 아님.
- 5종 graph/ETOT/OTG 실계산. timestamp ordering/tie 선택·qualifier·isolate 보존 명시. ETOT frequency populations·OTG undirected orientation 분리; runtime parity 아님.

**실제 함수·모델:** [relations.discover_otg](../../../src/pix/object_centric/relations.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

## OC-INTERLEAVINGS

**Linked-case temporal interleavings and networks**

### PM-OCEL-026

**업무 질문:** 연관된 두 case 로그의 교차 행동과 연결 사슬을 발견할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocel.util.log_ocel.from_interleavings`

**참조 선택지:** `TIMESTAMP_INTERLEAVINGS`, `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 연관된 두 case 표와 관계 key·timestamp·forward/propagation 옵션.

**검토 대상 결과:** Event interleavings·연결 사슬 및 통합 OCEL 대응.

**PIX 계산 정의:**

- 연결된 두 CaseLog의 시간 구간 crossing을 sweep하고 typed output/input link의 first/forward/transitive 관계를 계산한다. 원본 case/object와 모든 실제 event를 OCEL로 투영하며 cross E2O는 interleaving_candidate qualifier를 갖는다.

**입력 도메인 경계:** two explicit CaseLogs and case relations; derived OCEL is an explicit conversion

**남은 차이·검증 범위:**

- 이 계산은 CaseLog 입력에서 객체 관계 후보로 연결되는 bridge이며 OCEL을 case로 암묵 flatten하지 않는다. 시간 crossing은 인과 증명이 아니다. Primitive OCEL 투영 불가 속성은 실패/sidecar 보존하며 logical boundary는 실제 event로 생성하지 않는다.

**실제 함수·모델:** [interleavings.discover_interleavings](../../../src/pix/case_centric/interleavings.py), [interleavings_ocel.from_interleavings](../../../src/pix/case_centric/interleavings_ocel.py), [link_analysis.discover_link_analysis](../../../src/pix/case_centric/link_analysis.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/case_centric/test_interleavings.py](../../../tests/case_centric/test_interleavings.py)
- [tests/case_centric/test_interleavings_ocel.py](../../../tests/case_centric/test_interleavings_ocel.py)
- [tests/case_centric/test_link_analysis.py](../../../tests/case_centric/test_link_analysis.py)

</details>

## OC-TRANSFORMS

**Explicit flattening, enrichment, ordering, merge and graph views**

### PM-OCEL-004

**업무 질문:** 하나의 객체형을 case로 삼아 OCEL을 펼칠 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_flattening`, `pm4py.objects.ocel.util.flattening.flatten`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 선택 object type, ordering·attribute 정책.

**검토 대상 결과:** 객체를 case로 한 trace/table view와 공유 event lineage.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- object-type TraceSet 투영 존재; full attributed CaseLog flattening 미구현
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [trace.reconstruct_traces](../../../src/pix/compute/trace.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-008

**업무 질문:** 관측에서 유도한 객체 관계를 O2O에 추가할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_o2o_enrichment`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 포함할 유도 객체 graph 종류.

**검토 대상 결과:** 유도 O2O가 추가된 view와 원본·derived 관계의 구분.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- Five observed graph kinds now materialize qualified O2O with exact source witnesses and explicit directed/both/lexical handling; collision and isolate policy preserve source facts. Inferred graph is not original O2O truth.
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [enrichment.enrich_object_relations](../../../src/pix/object_centric/enrichment.py), [enrichment.materialize_enriched_ocel](../../../src/pix/object_centric/enrichment.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-009

**업무 질문:** 객체의 최초·최종 참여를 E2O lifecycle qualifier로 표시할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_e2o_lifecycle_enrichment`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL E2O 관계와 객체별 관측 순서.

**검토 대상 결과:** Creation/termination/other qualifier가 부여된 관계 view.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- First/last observed lifecycle role enrichment exists with reject/all_tied/event_id and both roles on singleton. Interior other-role classification is not implemented. Native enrichment preserves old qualifiers rather than PM overwrite behavior.
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [enrichment.mark_lifecycle_qualifiers](../../../src/pix/object_centric/enrichment.py), [enrichment.materialize_enriched_ocel](../../../src/pix/object_centric/enrichment.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-011

**업무 질문:** 동일 관측을 중복 제거하거나 event를 병합할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_drop_duplicates`, `pm4py.ocel.ocel_merge_duplicates`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 중복 key·공유 객체 조건.

**검토 대상 결과:** 중복 제거/병합 view와 원본 event/속성/관계 대응.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- Native exact-event/qualified-participation dedup and event merge with stable lineage/IDs, typed-attribute conflict policy and qualifier preservation. Does not reproduce reference role/attribute-dropping or random-ID behavior.
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [transformations.deduplicate_ocel](../../../src/pix/object_centric/transformations.py), [transformations.materialize_ocel_transformation](../../../src/pix/object_centric/transformations.py), [transformations.merge_ocel_events](../../../src/pix/object_centric/transformations.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-012

**업무 질문:** 동률 이벤트를 추가 속성으로 정렬하거나 명시적 순서로 처리할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_sort_by_additional_column`, `pm4py.ocel.ocel_add_index_based_timedelta`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 추가 정렬 key 또는 명시 tie policy.

**검토 대상 결과:** 순서 view 또는 합성 시각 변환본과 변경 근거.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- tie event_id 규칙만 있음; additional-column order·timestamp perturbation 없음
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [trace.reconstruct_traces](../../../src/pix/compute/trace.py), [features.encode_object_features](../../../src/pix/object_centric/features.py), [filtering.materialize_sublog](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-031

**업무 질문:** OCEL의 event/object/직접후속 또는 object feature 관계를 graph로 변환할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.convert.convert_ocel_to_networkx`

**참조 선택지:** `OCEL_TO_NX`, `OCEL_FEATURES_TO_NX`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 event/object graph 또는 object-feature graph variant.

**검토 대상 결과:** Typed event/object/DF 또는 object-feature relation graph.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- feature/EOG graph 존재; 통합 event/object/DF NetworkX 변환 계약 없음
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [trace.reconstruct_traces](../../../src/pix/compute/trace.py), [features.encode_object_features](../../../src/pix/object_centric/features.py), [filtering.materialize_sublog](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-032

**업무 질문:** 속성을 객체로 승격하거나 object-event 관계를 explode하고 부모–자식 참조를 만들 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocel.util.ev_att_to_obj_type.apply`, `pm4py.objects.ocel.util.explode.apply`, `pm4py.objects.ocel.util.parent_children_ref.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 승격할 속성·explode·parent/child 조건.

**검토 대상 결과:** 새 객체/관계/복제 event view와 원본 lineage.

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- Typed event-attribute promotion, one-clone-per-distinct-object explode and unique_parent/temporal parent-child evidence now exist. No coercive string identities or unreported parent overwrite; co-participation is candidate relation evidence.
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [transformations.explode_ocel](../../../src/pix/object_centric/transformations.py), [transformations.infer_parent_child_references](../../../src/pix/object_centric/transformations.py), [transformations.materialize_ocel_transformation](../../../src/pix/object_centric/transformations.py), [transformations.promote_event_attribute](../../../src/pix/object_centric/transformations.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-DATA-001

**업무 질문:** OCEL을 객체형별 case log로 투영하고 활동별 객체 수를 얻는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.util.project_log`, `ocpa.algo.util.util.project_log_with_object_count`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL table, 기준 객체형·column mapping

**검토 대상 결과:** 객체별 case log와 활동별 객체 참여 count 분포

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- TraceSet 투영+참여 수 primitives; full object-count log projection 없음
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [trace.reconstruct_traces](../../../src/pix/compute/trace.py).

<details>
<summary>관련 테스트 6개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-DATA-002

**업무 질문:** Succinct/exploded 표를 변환하고 활동·경로 빈도를 정리하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.log.importer.csv.util.succint_stream_to_exploded_stream`, `ocpa.objects.log.importer.csv.util.succint_mdl_to_exploded_mdl`, `ocpa.objects.log.importer.csv.util.clean_normalized_frequency`, `ocpa.objects.log.importer.csv.util.clean_frequency` 외 4개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Succinct/exploded 표, 빈도·경로·시각/객체 조건

**검토 대상 결과:** 변환/정리된 표와 원본 event/object 대응

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- Timestamp sublogs and native frequency selection now contribute; succinct/exploded table normalization and all path/arc-frequency cleanup outputs remain missing.
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [advanced_filtering.filter_ocel_frequency](../../../src/pix/object_centric/advanced_filtering.py), [filtering.filter_ocel](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-DATA-003

**업무 질문:** 여러 OCEL을 합치거나 실행을 표본 선택하고 참조 객체를 정리하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.util.util.merge_json`, `ocpa.objects.log.variants.table.Table.sample_cases`, `ocpa.objects.log.variants.table.Table.get_objects_of_variants`, `ocpa.objects.log.variants.table.Table.remove_object_references` 외 4개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 복수 OCEL/JSON 또는 원본 log, 표본/참조 선택

**검토 대상 결과:** 병합·복사·표본 sublog와 충돌·선택 이력

**PIX 계산 정의:**

- explicit_trace_projection
- source_fact_preserving_sublog
- typed_feature_graph
- exact_events
- qualified_participation
- unique_parent
- temporal
- both
- lexical
- all_tied
- skip_identical

**남은 차이·검증 범위:**

- Component sampling, execution/variant object selection and exact relation-pruning sublogs now exist. General multi-OCEL merge and all legacy table/copy signatures remain missing.
- Enrichment, lifecycle marking, dedup/merge, typed promotion/explode/parent-reference materialization now exist. Full attributed OCEL-to-CaseLog flattening, arbitrary order-column/timestamp perturbation, general OCEL merge and succinct/exploded normalization remain partial.

**실제 함수·모델:** [advanced_filtering.filter_ocel_executions](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.sample_ocel](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 7개 파일</summary>

- [tests/compute/test_trace.py](../../../tests/compute/test_trace.py)
- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_enrichment.py](../../../tests/object_centric/test_enrichment.py)
- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/object_centric/test_transformations.py](../../../tests/object_centric/test_transformations.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

## OC-OLAP

**OCEL drill-down/roll-up/fold/unfold**

### PM-OCEL-015

**업무 질문:** 객체 속성 값으로 타입을 세분화하거나 다시 묶을 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_drill_down`, `pm4py.ocel.ocel_roll_up`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 object type·분기 기준 속성.

**검토 대상 결과:** 세분화/집계된 object-type view와 원본 타입 대응.

**PIX 계산 정의:**

- drill_down
- roll_up
- unfold
- fold
- retain_parent
- reject

**남은 차이·검증 범위:**

- All four transformations now exist: explicit as-of typed drill-down, related-object-type event unfold, provenance-checked inverse roll-up/fold. Arbitrary callback naming/prefix merging and general OLAP aggregation are not reference-equivalent.
- All four transformations now exist: explicit as-of typed drill-down, related-object-type event unfold, provenance-checked inverse roll-up/fold. Arbitrary callback naming/prefix merging and general OLAP aggregation are not reference-equivalent.

**실제 함수·모델:** [cube.drill_down](../../../src/pix/object_centric/cube.py), [cube.materialize_cube](../../../src/pix/object_centric/cube.py), [cube.roll_up](../../../src/pix/object_centric/cube.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_cube.py](../../../tests/object_centric/test_cube.py)

</details>

### PM-OCEL-016

**업무 질문:** 객체 참여 정보를 event 타입에 펼쳤다가 되돌릴 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.ocel_unfold`, `pm4py.ocel.ocel_fold`

**참조 선택지:** `CLASSIC`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 event type·object type·qualifier 선택.

**검토 대상 결과:** 관계 정보를 펼치거나 접은 event-type view와 손실 보고.

**PIX 계산 정의:**

- drill_down
- roll_up
- unfold
- fold
- retain_parent
- reject

**남은 차이·검증 범위:**

- All four transformations now exist: explicit as-of typed drill-down, related-object-type event unfold, provenance-checked inverse roll-up/fold. Arbitrary callback naming/prefix merging and general OLAP aggregation are not reference-equivalent.
- All four transformations now exist: explicit as-of typed drill-down, related-object-type event unfold, provenance-checked inverse roll-up/fold. Arbitrary callback naming/prefix merging and general OLAP aggregation are not reference-equivalent.

**실제 함수·모델:** [cube.fold](../../../src/pix/object_centric/cube.py), [cube.materialize_cube](../../../src/pix/object_centric/cube.py), [cube.unfold](../../../src/pix/object_centric/cube.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_cube.py](../../../tests/object_centric/test_cube.py)

</details>

## OC-FILTERING

**Event/object/execution selection, closure, sampling and performance filters**

### PM-OCEL-010

**업무 질문:** Event·object·connected component 단위로 OCEL을 표본 추출할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ocel.sample_ocel_objects`, `pm4py.ocel.sample_ocel_connected_components`, `pm4py.objects.ocel.util.sampling.sample_ocel_events`, `pm4py.objects.ocel.util.sampling.sample_ocel_objects`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 표본 단위·개수·component 크기 한도·seed.

**검토 대상 결과:** 선택 ID 및 관계/이력 보존 범위를 가진 sampled OCEL.

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Seeded event/object/component sampling now exists with explicit projection/isolate and eligibility limits; source-defined implementation with dedicated sampling tests now present; final executed validation is recorded separately.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.sample_ocel](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-017

**업무 질문:** 이벤트·객체의 속성 조건과 시간 범위로 OCEL을 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_ocel_event_attribute`, `pm4py.filtering.filter_ocel_object_attribute`, `pm4py.filtering.filter_ocel_events_timestamp`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL event/object 속성 조건 또는 시간창.

**검토 대상 결과:** 조건 sublog와 관계 closure·객체 이력 경계 상태.

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Event time selection plus typed event/object attribute equals/numeric_range/present predicates now exist; object attributes require explicit fixed as-of and unknown policy.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_by_predicate](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py), [filter_predicates.evaluate_filter_predicates](../../../src/pix/object_centric/filter_predicates.py), [filtering.filter_ocel](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-018

**업무 질문:** 객체형·객체 ID·event ID를 선택하고 연결 범위를 조절할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_ocel_object_types`, `pm4py.filtering.filter_ocel_objects`, `pm4py.filtering.filter_ocel_events`, `pm4py.filtering.filter_ocel_activities_connected_object_type`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 object/event ID·type·연결 확대 깊이.

**검토 대상 결과:** 선택 객체/event 및 연결 범위를 보존한 sublog.

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- ID/type/activity seed와 명시 O2O depth closure
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [filtering.filter_ocel](../../../src/pix/object_centric/filtering.py), [filtering.materialize_sublog](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-019

**업무 질문:** 활동과 객체형 조합·참여 개수·형별 시작/종료 이벤트를 필터링할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_ocel_object_types_allowed_activities`, `pm4py.filtering.filter_ocel_object_per_type_count`, `pm4py.filtering.filter_ocel_start_events_per_object_type`, `pm4py.filtering.filter_ocel_end_events_per_object_type`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL과 활동×타입 허용표·참여 개수·관측 boundary 조건.

**검토 대상 결과:** 참여/시작/종료 조건을 만족하는 OCEL sublog.

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Activity/type E2O whitelist, unique-object or relation cardinality and observed start/end event selection now exist; timestamp ties explicit reject/all/event_id.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_structure](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-020

**업무 질문:** 특정 객체·크기·타입·활동이 있는 connected component만 선택할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.filtering.filter_ocel_cc_object`, `pm4py.filtering.filter_ocel_cc_length`, `pm4py.filtering.filter_ocel_cc_otype`, `pm4py.filtering.filter_ocel_cc_activity`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL component와 객체·크기·type·activity 조건.

**검토 대상 결과:** 조건에 맞는 connected components의 sublog.

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Connected-component/execution membership filters now accept object/type/activity and event/object/relation/duration ranges, with explicit isolate and overlap evidence.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_executions](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### PM-OCEL-034

**업무 질문:** 시점별 객체 상태·qualifier를 보존하고 조회 가능한 형식으로 전달할 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.objects.ocel.util.filtering_utils.propagate_event_filtering`, `pm4py.objects.ocel.util.filtering_utils.propagate_object_filtering`, `pm4py.objects.ocel.util.filtering_utils.propagate_relations_filtering`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL O2O/E2O·object assignment 이력과 선택 시점/필터.

**검토 대상 결과:** 보존된 관계/이력 sublog 및 제안 as-of 상태 조회 근거.

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- 선택 source facts의 참조 정합성/qualified relations와 history 보존
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [filtering.filter_ocel](../../../src/pix/object_centric/filtering.py), [filtering.materialize_sublog](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-001

**업무 질문:** 빈도가 낮은 활동·variant나 선택하지 않은 실행을 제거할 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.activity_filtering.filter_infrequent_activities`, `ocpa.algo.util.filtering.log.variant_filtering.filter_infrequent_variants`, `ocpa.algo.util.filtering.log.case_filtering.filter_process_executions`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 빈도 threshold 또는 execution 목록

**검토 대상 결과:** 선택 sublog와 포함/제외·관계 정리 근거

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Activity frequency and exact native variant-frequency/selected-execution filtering now exist; rank/count/share/coverage boundaries and tie expansion explicit.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_executions](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.filter_ocel_frequency](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-002

**업무 질문:** 시간창에 시작·끝·포함·겹침 조건을 만족하는 실행 또는 이벤트만 선택하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.time_filtering.start`, `ocpa.algo.util.filtering.log.time_filtering.spanning`, `ocpa.algo.util.filtering.log.time_filtering.end`, `ocpa.algo.util.filtering.log.time_filtering.contained` 외 3개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 시간창, start/end/spanning/contained/events 선택

**검토 대상 결과:** 시간 조건을 만족한 실행 또는 event sublog

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Event time windows and execution-duration ranges exist; execution start/spanning/end/contained relative-to-window selection is still not implemented.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_executions](../../../src/pix/object_centric/advanced_filtering.py), [filtering.filter_ocel](../../../src/pix/object_centric/filtering.py).

<details>
<summary>관련 테스트 3개 파일</summary>

- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-003

**업무 질문:** 활동·객체형 목록이나 빈도로 OCEL을 선택하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.index_based_filtering.activity_filtering`, `ocpa.algo.util.filtering.log.index_based_filtering.activity_freq_filtering`, `ocpa.algo.util.filtering.log.index_based_filtering.object_type_filtering`, `ocpa.algo.util.filtering.log.index_based_filtering.object_freq_filtering`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 활동·객체형 집합 또는 빈도 threshold

**검토 대상 결과:** 선택 sublog 및 정리된 객체 참조

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Activity/object/object-type frequency filters now exist with unique event/object versus qualified-relation populations and explicit rank/coverage thresholds.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_frequency](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-004

**업무 질문:** 이벤트·객체 속성 조건을 만족하는 데이터만 남기는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.index_based_filtering.event_attribute_filtering`, `ocpa.algo.util.filtering.log.index_based_filtering.object_attribute_filtering`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 이벤트/객체 속성 조건

**검토 대상 결과:** 조건에 맞는 sublog와 객체 이력·선택 lineage

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Typed event/object attribute predicates and actual sublog projection now exist; object as-of mandatory, bool/int/float equality distinct, missing truth explicitly controlled.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_by_predicate](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py), [filter_predicates.evaluate_filter_predicates](../../../src/pix/object_centric/filter_predicates.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-005

**업무 질문:** 객체 lifecycle에 지정한 활동들이 나타나는 관측만 선택하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.index_based_filtering.object_lifecycle_filtering`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 객체형, lifecycle 활동 조건

**검토 대상 결과:** 조건을 만족하는 객체와 관련 event sublog

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Single-activity object lifecycle start/end/contains/rework or duration predicates now exist with materialization. Arbitrary multi-activity lifecycle rule combinations and reference timestamp ordering are not all exposed.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_by_predicate](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py), [filter_predicates.evaluate_filter_predicates](../../../src/pix/object_centric/filter_predicates.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-006

**업무 질문:** EOG 성능 값이 조건에 맞는 이벤트만 선택하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.index_based_filtering.event_performance_based_filtering`

**참조 선택지:** 9개의 이름이 registry에 보존되어 있다. 이 행의 잔여 차이에서 지원 범위와 동등성의 제한을 구분한다.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, EOG 성능 measure·threshold·객체형

**검토 대상 결과:** 성능 조건을 만족하는 event sublog 및 측정 근거

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- One supported scalar event EOG metric can drive typed predicate and actual sublog. Multi-sample elapsed/remaining, activity aggregates and timed replay OPERA require separate aggregation/evidence and are not accepted.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_by_predicate](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py), [filter_predicates.evaluate_filter_predicates](../../../src/pix/object_centric/filter_predicates.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

### OC-FILTER-007

**업무 질문:** 빈도나 활동 sequence로 실행 variant를 선택하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.filtering.log.index_based_filtering.variant_infrequent_filtering`, `ocpa.algo.util.filtering.log.index_based_filtering.variant_activity_sequence_filtering`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL variant, threshold 또는 활동 sequence 목록

**검토 대상 결과:** 선택 variant·실행·이벤트와 overlap/빈도 coverage

**PIX 계산 정의:**

- conjunctive_source_fact_projection
- closed_time_window
- explicit_o2o_closure
- window_with_prior
- events
- objects
- components
- at_least
- exceed
- cardinality
- activity_type_matching
- start_events
- end_events
- conditions
- execution_ids
- variant_ids
- variant_frequency
- sequence
- event_attribute
- object_attribute
- object_lifecycle
- performance

**남은 차이·검증 범위:**

- Native exact incidence variant ID/frequency and explicit timestamp-linearized activity-sequence selection now exist. OCPA equivalence and implicit event-row ordering are not claimed.
- Basic immutable source-fact filtering plus seeded sampling, frequency/structure/execution/variant/sequence filters, typed as-of attribute/lifecycle/performance predicates and materialization now exist. Execution-window start/spanning/end/contained and some multi-value performance/lifecycle options remain partial. Dedicated advanced-filter calculation tests are now present; final executed validation is recorded separately.

**실제 함수·모델:** [advanced_filtering.filter_ocel_executions](../../../src/pix/object_centric/advanced_filtering.py), [advanced_filtering.materialize_advanced_sublog](../../../src/pix/object_centric/advanced_filtering.py).

<details>
<summary>관련 테스트 4개 파일</summary>

- [tests/object_centric/test_advanced_filtering.py](../../../tests/object_centric/test_advanced_filtering.py)
- [tests/object_centric/test_filter_predicates.py](../../../tests/object_centric/test_filter_predicates.py)
- [tests/object_centric/test_filtering.py](../../../tests/object_centric/test_filtering.py)
- [tests/test_mining_serialization.py](../../../tests/test_mining_serialization.py)

</details>

## OC-CONSTRAINTS

**Object/activity/cardinality/control-flow/performance rule semantics**

### OC-RULE-001

**업무 질문:** 객체형별 두 활동의 causal·concurrent·choice·skip 강도가 규칙을 만족하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.constraint_monitoring.versions.log_based.evaluate_cf_edge`

**참조 선택지:** `log_based`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ConstraintGraph CF edge, OCEL, 객체형/threshold

**검토 대상 결과:** 규칙별 충족 여부·관계 강도·분모와 witness

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-002

**업무 질문:** 활동 이벤트의 객체 부재·참여·한 개·여러 개 비율이 규칙을 만족하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.constraint_monitoring.versions.log_based.evaluate_or_edge`

**참조 선택지:** `log_based`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ConstraintGraph object edge, OCEL, 객체형/threshold

**검토 대상 결과:** Event 객체 참여 cardinality 비율 및 규칙 판정

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-003

**업무 질문:** 모델의 진단 성능값이 지정한 비교식·threshold를 만족하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.constraint_monitoring.versions.log_based.evaluate_perf_edge`

**참조 선택지:** `log_based`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ConstraintGraph performance edge, model diagnostics

**검토 대상 결과:** 비교식 판정·측정값/threshold와 미평가 원인

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-004

**업무 질문:** 확장 constraint graph의 OA·AA·AOA 규칙과 성능 조합을 평가하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.conformance.constraint_monitoring.versions.extensive_log_based.calculate_metric`, `ocpa.algo.conformance.constraint_monitoring.versions.extensive_log_based.compare`, `ocpa.algo.conformance.constraint_monitoring.versions.extensive_log_based.evaluate_oa_edge`, `ocpa.algo.conformance.constraint_monitoring.versions.extensive_log_based.evaluate_aa_edge` 외 1개(전체는 registry)

**참조 선택지:** `extensive_log_based`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ExtensiveConstraintGraph, OCEL, 집계/threshold

**검토 대상 결과:** OA/AA/AOA edge별 판정·수치·근거와 전체 평가

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-005

**업무 질문:** 활동 존재·부재·동시 존재·배타·선택·XOR를 만족하는 객체와 비율은 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.log.variants.obj.ObjectCentricEventLog.existence`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.existence_metric`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.non_existence`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.non_existence_metric` 외 8개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL object traces, 객체형과 활동 조건

**검토 대상 결과:** 조건을 만족하는 객체 ID 집합 및 모집단 비율

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-006

**업무 질문:** 객체별 followed-by·directly-followed-by·precedence·block 조건의 대상과 비율은 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.log.variants.obj.ObjectCentricEventLog.followed_by`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.followed_by_metric`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.directly_followed_by`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.directly_followed_by_metric` 외 4개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL object traces, 객체형·두 활동·순서 조건

**검토 대상 결과:** 순서 조건의 객체 ID 집합과 비율·반례

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-007

**업무 질문:** 활동 이벤트의 객체 참여 cardinality와 객체형별 관계 강도는 얼마인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.log.variants.obj.ObjectCentricEventLog.object_absence`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.object_absence_metric`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.object_singular`, `ocpa.objects.log.variants.obj.ObjectCentricEventLog.object_singular_metric` 외 9개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 활동·객체형 또는 두 활동

**검토 대상 결과:** 객체 cardinality별 이벤트 집합/비율 및 관계 강도

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- Native explicit rule/graph calculation exists under the documented closed-log population and occurrence profiles; reference runtime parity is not claimed.
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

### OC-RULE-008

**업무 질문:** Constraint graph 구조를 데이터에서 만들고 규칙 근거로 연결할 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.graph.constraint_graph.obj.ConstraintGraph`, `ocpa.objects.graph.constraint_graph.obj.ActivityNode`, `ocpa.objects.graph.constraint_graph.obj.ObjectTypeNode`, `ocpa.objects.graph.constraint_graph.obj.FormulaNode` 외 7개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 규칙 node/edge·formula를 담은 구조화 데이터

**검토 대상 결과:** Constraint graph 모델과 계산·시각화용 ID 관계

**PIX 계산 정의:**

- closed_observed_log
- every_activation
- first_occurrence
- unique_qualified_participation

**남은 차이·검증 범위:**

- validated typed graph contracts 존재; 데이터에서 constraint graph를 발견하는 API 없음
- Boolean/order/participation·CF/OA/AA/AOA/OR/PERF explicit graph predicates 계산. empty unknown, numerical negation/comparison bugs corrected; true=조건 성립이며 자동 violation 아님.

**실제 함수·모델:** [constraints.evaluate_constraint_graph](../../../src/pix/object_centric/constraints.py), [constraints.measure_rule_metric](../../../src/pix/object_centric/constraints.py), [constraints.performance_observations](../../../src/pix/object_centric/constraints.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)

</details>

## OC-QUALIFIERS

**E2O/O2O qualifier conformance and event-time object state**

### OC-REL-001

**업무 질문:** 특정 E2O qualifier로 참여한 객체 속성이 허용 조건에 맞는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.ocel2_use_cases.e2o_qualifier_conformance.e2o_qualifier_conformance`, `ocpa.algo.ocel2_use_cases.e2o_qualifier_conformance.find_last_appearance_value`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL2, activity/object type/E2O qualifier/속성 조건

**검토 대상 결과:** 허용·비허용 참여 수, 객체/event/속성 조회 근거

**PIX 계산 정의:**

- event_as_of
- latest_observed
- directed_o2o

**남은 차이·검증 범위:**

- E2O attr-state qualifier·event-wise O2O directed relation 판단과 witness. latest_observed와 event_as_of 명시 분리; untimed O2O lifetime은 추정 안 함.
- E2O attr-state qualifier·event-wise O2O directed relation 판단과 witness. latest_observed와 event_as_of 명시 분리; untimed O2O lifetime은 추정 안 함.

**실제 함수·모델:** [constraints.evaluate_e2o_qualifiers](../../../src/pix/object_centric/constraints.py), [constraints.evaluate_o2o_qualifiers](../../../src/pix/object_centric/constraints.py), [relations.object_attributes_as_of](../../../src/pix/object_centric/relations.py), [relations.query_object_relations](../../../src/pix/object_centric/relations.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

### OC-REL-002

**업무 질문:** 이벤트에 참여한 source×target 객체 쌍의 O2O qualifier가 허용 관계인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.ocel2_use_cases.o2o_qualifier_conformance.check_o2o_qualifier_conformance`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL2, activity/source·target 객체형, O2O qualifier

**검토 대상 결과:** 관계별 허용·비허용/부재 객체쌍 occurrence 수

**PIX 계산 정의:**

- event_as_of
- latest_observed
- directed_o2o

**남은 차이·검증 범위:**

- E2O attr-state qualifier·event-wise O2O directed relation 판단과 witness. latest_observed와 event_as_of 명시 분리; untimed O2O lifetime은 추정 안 함.
- E2O attr-state qualifier·event-wise O2O directed relation 판단과 witness. latest_observed와 event_as_of 명시 분리; untimed O2O lifetime은 추정 안 함.

**실제 함수·모델:** [constraints.evaluate_e2o_qualifiers](../../../src/pix/object_centric/constraints.py), [constraints.evaluate_o2o_qualifiers](../../../src/pix/object_centric/constraints.py), [relations.object_attributes_as_of](../../../src/pix/object_centric/relations.py), [relations.query_object_relations](../../../src/pix/object_centric/relations.py).

<details>
<summary>관련 테스트 2개 파일</summary>

- [tests/object_centric/test_constraints.py](../../../tests/object_centric/test_constraints.py)
- [tests/object_centric/test_relations.py](../../../tests/object_centric/test_relations.py)

</details>

## OC-FEATURES

**Object/event/execution/prefix features with named population profiles**

### PM-OCEL-027

**업무 질문:** 객체별 활동열·관계 graph·속성·work-in-progress를 feature로 만들 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.ml.extract_ocel_features`, `pm4py.algo.transformation.ocel.features.objects.algorithm.transform_features_to_dict_dict`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 객체 표본·feature 선택·관측 cutoff·vocabulary.

**검토 대상 결과:** 객체별 이름·단위·mask가 있는 feature 행렬과 근거.

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### PM-OCEL-028

**업무 질문:** 이벤트의 시각·활동·참여 객체와 신규 관계를 feature로 만들 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.ocel.features.events.algorithm.transform_features_to_dict_dict`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL event와 pointwise/관련 객체 feature 선택·cutoff.

**검토 대상 결과:** Event별 activity/time/attribute/relation feature 행렬.

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### PM-OCEL-029

**업무 질문:** 각 event–object 참여 시점까지의 prefix feature를 만들 수 있는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.transformation.ocel.features.events_objects.algorithm.apply`, `pm4py.algo.transformation.ocel.features.events_objects.prefix_features.apply`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL의 event–object participation과 prefix feature 선택.

**검토 대상 결과:** 각 참여 시점까지의 길이·시간·활동 prefix feature.

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-001

**업무 질문:** 이벤트 시점에 활동·객체·이전 행동·속성의 feature를 만들 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.number_of_objects`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.event_activity`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.event_identity`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.event_type_count` 외 10개(전체는 registry)

**참조 선택지:** 14개의 이름이 registry에 보존되어 있다. 이 행의 잔여 차이에서 지원 범위와 동등성의 제한을 구분한다.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, event feature spec, 관측 cutoff

**검토 대상 결과:** 14종 활동·객체·과거속성 feature 값과 근거

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-002

**업무 질문:** Service·실행 기간·elapsed·remaining·synchronization 등의 event feature를 만들 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.service_time`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.execution_duration`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.elapsed_time`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.remaining_time` 외 6개(전체는 registry)

**참조 선택지:** 10개의 이름이 registry에 보존되어 있다. 이 행의 잔여 차이에서 지원 범위와 동등성의 제한을 구분한다.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, time feature spec, 관측 cutoff/target horizon

**검토 대상 결과:** 10종 event 시간 feature와 input/target 구분

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-003

**업무 질문:** 현재 자원·전체 workload와 이벤트 자원 feature는 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.current_resource_workload`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.current_total_workload`, `ocpa.algo.predictive_monitoring.event_based_features.extraction_functions.event_resource`

**참조 선택지:** `event_current_resource_workload`, `event_current_total_workload`, `event_resource`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL resource/interval, workload feature spec

**검토 대상 결과:** 3종 자원·현재 workload feature

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-004

**업무 질문:** 실행별 크기·경계·기간·객체·활동·서비스 feature는 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.execution_based_features.extraction_functions.number_of_events`, `ocpa.algo.predictive_monitoring.execution_based_features.extraction_functions.number_of_ending_events`, `ocpa.algo.predictive_monitoring.execution_based_features.extraction_functions.throughput_time`, `ocpa.algo.predictive_monitoring.execution_based_features.extraction_functions.execution` 외 6개(전체는 registry)

**참조 선택지:** 10개의 이름이 registry에 보존되어 있다. 이 행의 잔여 차이에서 지원 범위와 동등성의 제한을 구분한다.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL execution, feature spec, 관측 완결성

**검토 대상 결과:** 10종 execution 크기·기간·경계·서비스 feature

**PIX 계산 정의:**

- unique_participation_per_execution_microseconds
- strict_before
- through_timestamp

**남은 차이·검증 범위:**

- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.
- Event/Object/Prefix/Execution 실계산; OCPA 27event+10execution branches와 PM 관계 feature 포함. shared event 여러 실행 평균 대신 실행별 row; no-future input와 retrospective target 분리; reference output 동일성 아님.

**실제 함수·모델:** [features.aggregate_object_features](../../../src/pix/object_centric/features.py), [features.extract_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

## OC-FEATURE-DATASET

**Feature graph, normalized split and tabular/sequential/time-series encoders**

### OC-FEAT-005

**업무 질문:** Event/execution feature를 graph로 저장하고 train/test 변환을 fit할 수 있는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.obj.Feature_Storage`, `ocpa.algo.predictive_monitoring.obj.Feature_Storage.Feature_Graph`, `ocpa.algo.predictive_monitoring.obj.Feature_Storage.add_feature_graph`, `ocpa.algo.predictive_monitoring.obj.Feature_Storage.extract_normalized_train_test_split`

**참조 선택지:** `event_based`, `execution_based`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, feature spec, scaler/encoder, split 비율

**검토 대상 결과:** Feature storage/graph와 train-fit 변환·train/validation/test

**PIX 계산 정의:**

- tabular
- sequence
- graph
- time_window
- shared_entity_partition
- training_rows_only

**남은 차이·검증 범위:**

- Feature graph and fitted train/test processing exist with explicit shared-entity partition and training-only fit.
- graph/table/sequence/time-series 및 leakage-aware split·numeric standardization·vocabulary fit 존재. 선형회귀 학습·MAE·k-step sample target 별도 API 없음.

**실제 함수·모델:** [features.encode_object_features](../../../src/pix/object_centric/features.py), [features.fit_object_feature_encoder](../../../src/pix/object_centric/features.py), [features.split_object_features](../../../src/pix/object_centric/features.py), [features.transform_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-006

**업무 질문:** Feature graph를 event 행의 표로 인코딩하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.tabular.construct_table`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Feature storage, 선택 graph/event index

**검토 대상 결과:** Event 행×feature 열 테이블

**PIX 계산 정의:**

- tabular
- sequence
- graph
- time_window
- shared_entity_partition
- training_rows_only

**남은 차이·검증 범위:**

- Typed table encoding exists; OCPA DataFrame output parity is not claimed.
- graph/table/sequence/time-series 및 leakage-aware split·numeric standardization·vocabulary fit 존재. 선형회귀 학습·MAE·k-step sample target 별도 API 없음.

**실제 함수·모델:** [features.encode_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-007

**업무 질문:** Feature를 sequence와 길이 k 학습 표본/target으로 만드는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.sequential.construct_sequence`, `ocpa.algo.predictive_monitoring.sequential.construct_k_dataset`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Feature storage/sequence, k·feature·target 선택

**검토 대상 결과:** Event feature sequence 및 길이 k 학습 표본·target

**PIX 계산 정의:**

- tabular
- sequence
- graph
- time_window
- shared_entity_partition
- training_rows_only

**남은 차이·검증 범위:**

- timestamp-block sequence 제공; construct_k_dataset 대응 sample/target 생성 없음
- graph/table/sequence/time-series 및 leakage-aware split·numeric standardization·vocabulary fit 존재. 선형회귀 학습·MAE·k-step sample target 별도 API 없음.

**실제 함수·모델:** [features.encode_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-008

**업무 질문:** 시간창별 event/execution feature를 집계한 시계열을 만드는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.predictive_monitoring.time_series.construct_time_series`

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCEL, 시간창 w, event/case feature·포함 전략

**검토 대상 결과:** 시간창별 집계 feature 시계열

**PIX 계산 정의:**

- tabular
- sequence
- graph
- time_window
- shared_entity_partition
- training_rows_only

**남은 차이·검증 범위:**

- Half-open time-window row-membership aggregation exists.
- graph/table/sequence/time-series 및 leakage-aware split·numeric standardization·vocabulary fit 존재. 선형회귀 학습·MAE·k-step sample target 별도 API 없음.

**실제 함수·모델:** [features.encode_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

### OC-FEAT-009

**업무 질문:** Feature 표준화·선형 회귀·MAE 계산을 제공하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.util.util.StandardScaler`, `ocpa.util.util.StandardScaler.fit`, `ocpa.util.util.StandardScaler.transform`, `ocpa.util.util.StandardScaler.fit_transform` 외 5개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** 수치 행렬 X·y 또는 예측/실제값

**검토 대상 결과:** 표준화 값/역변환·회귀 계수/예측·MAE

**PIX 계산 정의:**

- tabular
- sequence
- graph
- time_window
- shared_entity_partition
- training_rows_only

**남은 차이·검증 범위:**

- training numeric mean/std와 transform 있음; inverse_transform/linear regression/predict/MAE 없음
- graph/table/sequence/time-series 및 leakage-aware split·numeric standardization·vocabulary fit 존재. 선형회귀 학습·MAE·k-step sample target 별도 API 없음.

**실제 함수·모델:** [features.fit_object_feature_encoder](../../../src/pix/object_centric/features.py), [features.transform_object_features](../../../src/pix/object_centric/features.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_features.py](../../../tests/object_centric/test_features.py)

</details>

## OC-OCPN-SIMULATION

**Object-centric Petri-net finite binding playout**

### PM-SIM-007

**업무 질문:** Object-centric Petri net의 실제 객체 binding 실행을 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.simulation.playout.ocpn.algorithm.apply`

**참조 선택지:** `EXTENSIVE`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OCPN·초기/최종 OC marking과 activity별 binding·branching 한도.

**검토 대상 결과:** 유효 binding sequence, OCEL 또는 허용 실행 존재 판정.

**PIX 계산 정의:**

- exhaustive
- sampled_uniform_concrete_enabled_bindings
- explicit_finite_object_final_marking

**남은 차이·검증 범위:**

- 실제 concrete binding path simulation. 참조 memoized marking/firing-count graph, per-activity limits, custom final predicate와 다름; clock/E2O qualifier를 날조한 OCEL 미출력.
- 실제 concrete binding path simulation. 참조 memoized marking/firing-count graph, per-activity limits, custom final predicate와 다름; clock/E2O qualifier를 날조한 OCEL 미출력.

**실제 함수·모델:** [simulation.playout_ocpn](../../../src/pix/object_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_simulation.py](../../../tests/object_centric/test_simulation.py)

</details>

## OC-OCCN-SIMULATION

**Object-centric causal-net finite marker-group playout**

### PM-SIM-008

**업무 질문:** Object-centric causal net의 객체 binding 실행을 생성하는가?

**대표 참조 이름:** pm4py 2.7.23.8 · `pm4py.algo.simulation.playout.oc_causal_net.algorithm.apply`

**참조 선택지:** `EXTENSIVE`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** OC causal net·객체 집합과 binding/branching 한도.

**검토 대상 결과:** 유효 객체 binding sequence 또는 생성한 OCEL.

**PIX 계산 정의:**

- pix.finite_object_obligation_net.v1
- exhaustive
- sampled_uniform_concrete_enabled_bindings

**남은 차이·검증 범위:**

- 진짜 causal obligation binding 직접 playout; OCPN 변환 재사용 아님. PM START_ 객체 초기화·전체 marker semantics·OCEL export 동등성 아님.
- 진짜 causal obligation binding 직접 playout; OCPN 변환 재사용 아님. PM START_ 객체 초기화·전체 marker semantics·OCEL export 동등성 아님.

**실제 함수·모델:** [simulation.playout_causal_net](../../../src/pix/object_centric/simulation.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_simulation.py](../../../tests/object_centric/test_simulation.py)

</details>

## OC-ACTION-PATTERNS

**Temporal constraint pattern matching and action candidates**

### OC-ACT-001

**업무 질문:** Constraint interval pattern에 맞는 action 후보를 찾는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.latest_end_date`, `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.generate_all_possible_mappings`, `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.complete_allens_relation`, `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.allens_relation` 외 1개(전체는 registry)

**참조 선택지:** `temporal_pattern_based`.

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Constraint instances, temporal pattern/action graph

**검토 대상 결과:** Pattern match 근거와 action 후보·기간

**PIX 계산 정의:**

- strict_13_allen_relations
- bounded_first_witness_pattern_matching

**남은 차이·검증 범위:**

- positive-duration strict Allen, explicit reuse/shared-object, bounded first witness. source loose interval bugs·암묵적 object join 재현 안 함. exhaustive candidate enumeration/optimal selection 아님.
- positive-duration strict Allen, explicit reuse/shared-object, bounded first witness. source loose interval bugs·암묵적 object join 재현 안 함. exhaustive candidate enumeration/optimal selection 아님.

**실제 함수·모델:** [actions.allen_relation](../../../src/pix/object_centric/actions.py), [actions.propose_actions](../../../src/pix/object_centric/actions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_actions.py](../../../tests/object_centric/test_actions.py)

</details>

## OC-ACTION-SCHEDULE

**Action precedence/conflicts and schedule metrics**

### OC-ACT-002

**업무 질문:** 후보 action들의 선행·충돌 조건을 지키는 일정과 waiting/flow/makespan은 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.create_action_conflict`, `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.instantiate_action_conflict`, `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.complete`, `ocpa.algo.util.aopm.action_engine.versions.temporal_pattern_based.plan_actions` 외 3개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Action 후보, precedence/conflict, 시간 단위

**검토 대상 결과:** 가능 일정·action instance, makespan/waiting/flow와 제외 사유

**PIX 계산 정의:**

- deterministic_precedence_ready_list_scheduling

**남은 차이·검증 범위:**

- release/deadline/conflict/cycle 증거와 no-action 선택. heuristic deadline 실패는 heuristic_incomplete; global optimum 아님.
- release/deadline/conflict/cycle 증거와 no-action 선택. heuristic deadline 실패는 heuristic_incomplete; global optimum 아님.

**실제 함수·모델:** [actions.schedule_actions](../../../src/pix/object_centric/actions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_actions.py](../../../tests/object_centric/test_actions.py)

</details>

## OC-ACTION-IMPACT

**Structural, marking and observed performance impact**

### OC-ACT-003

**업무 질문:** Action이 구조상 전후 활동과 객체형에 미치는 영향 범위는 무엇인가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.type_specific_FSA`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.backward_pass_FSA`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.forward_pass_FSA`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.direct_OSA` 외 5개(전체는 registry)

**참조 선택지:** `action_interface_model_based`.

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ActionChange, OCPN/action interface

**검토 대상 결과:** 활동·객체형별 직접/선행/후행 구조 영향 집합·수량

**PIX 계산 정의:**

- typed_structural_reachability
- supplied_marking
- change_minus_reference_half_open_windows
- opaque_rule_assignment_replacement

**남은 차이·검증 범위:**

- 구조·제공된 marking 객체군·관측창 delta·immutable config 변경. causal effect, 실제 action 실행, log→현재 marking 추정 없음.
- 구조·제공된 marking 객체군·관측창 delta·immutable config 변경. causal effect, 실제 action 실행, log→현재 marking 추정 없음.

**실제 함수·모델:** [actions.structural_action_impact](../../../src/pix/object_centric/actions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_actions.py](../../../tests/object_centric/test_actions.py)

</details>

### OC-ACT-004

**업무 질문:** Action 시점의 marking과 관련 subnet에 어떤 객체가 영향을 받는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.backward_pass_OIA`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.forward_pass_OIA`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.compute_marking`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.new_compute_marking` 외 1개(전체는 registry)

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ActionChange, OCEL·OCPN, 관측 시점 marking

**검토 대상 결과:** 관련 subnet의 전후 영향 객체 집합·수량

**PIX 계산 정의:**

- typed_structural_reachability
- supplied_marking
- change_minus_reference_half_open_windows
- opaque_rule_assignment_replacement

**남은 차이·검증 범위:**

- supplied marking population만 계산; operational marking estimation 없음
- 구조·제공된 marking 객체군·관측창 delta·immutable config 변경. causal effect, 실제 action 실행, log→현재 marking 추정 없음.

**실제 함수·모델:** [actions.compare_action_windows](../../../src/pix/object_centric/actions.py), [actions.structural_action_impact](../../../src/pix/object_centric/actions.py), [actions.update_action_configuration](../../../src/pix/object_centric/actions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_actions.py](../../../tests/object_centric/test_actions.py)

</details>

### OC-ACT-005

**업무 질문:** Action 전후 관측창에서 활동·객체 성능이 얼마나 달라졌는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.FPA`, `ocpa.algo.util.aopm.impact_analysis.versions.action_interface_model_based.OPA`, `ocpa.objects.aopm.impact.obj.FunctionWisePerformanceImpact.quantify`, `ocpa.objects.aopm.impact.obj.ObjectWisePerformanceImpact.quantify`

**현재 상태:** `partial` — 일부 기능 또는 제한된 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** ActionChange의 관측창·비교창, OCEL, measure/aggregation

**검토 대상 결과:** FPA/OPA 성능 차이·부호/모집단·결측 원인

**PIX 계산 정의:**

- typed_structural_reachability
- supplied_marking
- change_minus_reference_half_open_windows
- opaque_rule_assignment_replacement

**남은 차이·검증 범위:**

- 구조·제공된 marking 객체군·관측창 delta·immutable config 변경. causal effect, 실제 action 실행, log→현재 marking 추정 없음.
- 구조·제공된 marking 객체군·관측창 delta·immutable config 변경. causal effect, 실제 action 실행, log→현재 marking 추정 없음.

**실제 함수·모델:** [actions.compare_action_windows](../../../src/pix/object_centric/actions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_actions.py](../../../tests/object_centric/test_actions.py)

</details>

### OC-ACT-006

**업무 질문:** Constraint instance와 action interface의 설정을 교환하고 변경을 계산하는가?

**대표 참조 이름:** ocpa 1.3.4 · `ocpa.objects.aopm.action_interface_model.obj.ActionInterfaceModel`, `ocpa.objects.aopm.action_interface_model.obj.ActionInterfaceModel.to_dict`, `ocpa.objects.aopm.action_interface_model.obj.Configuration`, `ocpa.objects.aopm.action_interface_model.obj.OperationalState` 외 8개(전체는 registry)

**현재 상태:** `native_profile` — 명시한 PIX 정의의 직접 계산. 참조 전체 대체 검증은 미완료다.

**검토 대상 입력:** Constraint instance 파일, action/interface/configuration 정의

**검토 대상 결과:** 구조화 instance·action 계약 및 configuration 변경값

**PIX 계산 정의:**

- typed_structural_reachability
- supplied_marking
- change_minus_reference_half_open_windows
- opaque_rule_assignment_replacement

**남은 차이·검증 범위:**

- integrity/reaction/derivation metadata assignment delta; rule expression 실행 아님
- 구조·제공된 marking 객체군·관측창 delta·immutable config 변경. causal effect, 실제 action 실행, log→현재 marking 추정 없음.

**실제 함수·모델:** [actions.update_action_configuration](../../../src/pix/object_centric/actions.py).

<details>
<summary>관련 테스트 1개 파일</summary>

- [tests/object_centric/test_actions.py](../../../tests/object_centric/test_actions.py)

</details>

---

이 문서는 현재 코드가 계산하는 정의와 남은 차이를 행별로 검토하는 자료이며, Object-Centric 참조 알고리즘의 모든 변형이 대체되었다는 판정은 아니다.
