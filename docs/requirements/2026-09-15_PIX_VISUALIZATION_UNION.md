# PIX 시각화 합집합: 구현 구조와 대체 범위

2026-09-15 실행 결과는 [당시 통합 검증 기록](../version/2026-09-15_NATIVE_VISUALIZATION_VALIDATION.md)에 별도로 남겼다. **2026-09-16 사용자 결정으로 모든 graph의 기본 배치는 Graphviz로 변경하고 OC variant chevron을 추가한다.** 새 요구와 인수 조건은 [변경 요구사항](2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md)을 따른다. 과거 테스트 수는 이 변경의 검증 결과가 아니다.

작성 기준일: **2026-09-15**. 참조 기준은 **PM4Py 2.7.23.8 / OCPA 1.3.4**의 고정 wheel 소스다. PIX의 계산을 이 라이브러리에서 실행한 뒤 그림만 바꾸는 구조가 아니라, PIX 계산 결과를 PIX의 시각화 계약으로 연결하는 구조를 다룬다. 사용 방법은 [시각화 가이드](../user-guide/VISUALIZATION_GUIDE.md)에 있다.

## 조사에서 확인한 사실

2026-09-15까지 기존 PIX viewer는 자체 SVG 화면에 ELK.js 0.12.0 배치를, 신규 문서는 PIX 자체 배치를 사용했다. 이후 DFG 2개·OCDFG 2개 합성 로그 화면에서 간선·라벨이 겹쳐 읽기 어려운 사례가 확인되었다. 따라서 자체 배치를 기본으로 유지한다는 당시 선택은 철회했다. 기존 계산 계약과 SVG 화면은 유지하면서 배치 책임을 Graphviz에 맡긴다.

PM4Py의 시각화가 모두 Graphviz를 쓰는 것은 아니다. 고정 소스에는 BPMN의 Dagre.js·bpmn.io, OCDFG의 ELK.js, SNA의 NetworkX/matplotlib·PyVis 경로도 있다. OCPA의 constraint graph는 Cytoscape 요소 데이터, chevron은 좌표 데이터, OC alignment는 matplotlib 그림을 반환한다. 따라서 하나의 renderer를 교체하는 작업과 도메인별 표현을 다시 만드는 작업은 구분했다.

조사 원본은 [의미별 인벤토리](../../.artifacts/visualization-2026-09-15/reference-inventory.md)와 [소스 색인](../../.artifacts/visualization-2026-09-15/reference-source-index.json)에 있다. 색인에는 함수·signature·variant·import와 파일 SHA-256이 들어 있다. 두 라이브러리를 설치·import·실행하여 출력의 동등성을 검사한 자료는 아니다. 아래 **26행은 검토 단위**이며, 알고리즘 수나 완성률의 분모가 아니다.

## 구조 선택과 근거

신규 `VisualizationDocument`의 graph panel과 기존 `GraphDocument`·`ModelGraphDocument` 모두 **Graphviz 배치 + PIX SVG/HTML**을 기본으로 사용한다. `@viz-js/viz` 3.30.0이 제공하는 Graphviz 16.0.0 WebAssembly를 wheel과 HTML에 포함한다. 이는 Graphviz 의존성이 없다는 뜻이 아니라, 사용자에게 별도 `dot` 실행 파일이나 Python `graphviz` 설치를 요구하지 않는 배포 방식이다. 기존 엄격한 OCDFG·PN 계약을 범용 그래프로 느슨하게 바꾸지는 않는다. [Viz.js 공식 API](https://viz-js.com/api/)

| 선택지 | 확인한 성격 | 이번 적용과 남는 판단 |
|---|---|---|
| 기존 배치 설정 유지 | 구현 변경 없이 기존 출력을 유지할 수 있음 | 실제 샘플의 간선·라벨 혼잡과 사용자의 기본값 변경 지시로 채택하지 않음 |
| Graphviz 배치 + PIX SVG | Graphviz가 node 위치·spline·label 좌표를 계산하고 PIX가 의미·ID·상호작용을 유지 | **모든 graph 문서의 기본값**. WebAssembly를 동봉하며 실행 시 네트워크 불필요. 품질은 동일 샘플의 변경 전후 화면으로 검토 |
| PIX 자체 배치 | 외부 graph 배치 없이 layered·tree·force·bipartite 좌표를 계산 | 신규 문서에서 `layout_engine="native"`로만 선택하는 실험 경로. 기본값·자동 fallback으로 사용하지 않음 |
| ELK 배치 어댑터 | port, label, edge routing, 간격 등 세부 배치 옵션이 있음 | 기존 두 graph 문서에서 `layout_engine="elk"`로만 명시 선택. 신규 문서의 ELK 요청은 거부. [ELK 옵션](https://eclipse.dev/elk/reference/options.html), [간격 계약](https://eclipse.dev/elk/documentation/tooldevelopers/graphdatastructure/spacingdocumentation.html) |
| Cytoscape.js | 그래프 모델·화면 상호작용·확장 가능한 layout 체계 제공 | 향후 전용 graph 탐색 화면의 후보. 이번 신규 실행 경로에 의존성으로 추가하지 않음. [공식 문서](https://js.cytoscape.org/) |
| Sigma.js | Graphology와 함께 WebGL 그래프 렌더링을 제공 | 대형 object instance graph의 별도 화면 후보. 일반 graph 표현 능력만으로 PN·부분순서·OC shared-event 의미가 자동 보존되지는 않음. [공식 문서](https://www.sigmajs.org/docs/) |

이 선택은 Graphviz가 모든 입력에서 더 좋은 그림을 보장한다는 주장이 아니다. 엔진 간 속도, 읽기 쉬움, 최대 실용 데이터 크기의 보편적 비교 수치는 **알 수 없음**이다. 대상 데이터에서 교차·겹침·선택 지연이 사용 기준을 만족하지 못하면 해당 설정과 배치 어댑터를 재검토한다. 실행 실패는 화면에 드러내며 다른 엔진으로 조용히 전환하지 않는다.

## 도메인 의미가 화면에 도달하는 과정

| 계층 | PIX 소유 계약 | 도메인적으로 보존하는 것 |
|---|---|---|
| 계산 | 기존 CC / OC 결과와 모델 | 발견·정렬·재생·성능 계산의 정의, 대상 집합, 계산 한도와 상태 |
| 도메인 어댑터 | [CC](../../src/pix/viewer/visual_case_adapters.py), [OC](../../src/pix/viewer/visual_object_adapters.py), [모델](../../src/pix/viewer/visual_model_adapters.py), [발견·변환 결과](../../src/pix/viewer/visual_model_results.py), [주석](../../src/pix/viewer/visual_annotations.py) | 모델 종류, 사건·객체·전이 ID, 계산 근거, 단위, 알려지지 않은 값 |
| 시각화 문서 | [VisualizationDocument](../../src/pix/viewer/visual_contracts.py) | graph / matrix / chart / timeline / chevron / table을 구분하는 불변 자료형. source·model·calculation 출처와 부분 결과 상태 |
| graph 배치 | Graphviz WebAssembly와 PIX geometry 어댑터 | node·edge ID, 평행 간선·자기 루프를 유지한 node 위치·spline·label 좌표. 계산 코어와 독립 |
| chevron 배치 | 실행의 선행관계로 정의한 정수 슬롯 | 객체 instance lane, shared event의 동일한 시작·끝 슬롯. Graphviz의 임의 graph 좌표나 실제 소요시간과 구별 |
| 화면 | [자체 SVG/HTML renderer](../../src/pix/viewer/assets/visualization.js) | 선택·확대·검색·범례·근거 inspector, 원래 수치와 화면 축의 구분 |
| 저장 | [HTML](../../src/pix/viewer/export.py), [시각화 JSON](../../src/pix/viewer/visual_serialization.py) | 오프라인 HTML, 화면 SVG, 다시 읽을 수 있는 시각화 데이터 |

예를 들어 OCPN에서 두 객체가 같은 전이에 함께 참여하면, 모델의 전이는 하나이고 객체 참여가 여러 개다. OC alignment에서도 공동 move의 비용은 한 번 기록하고, 객체 lane에는 같은 move를 참조하는 여러 표시를 둔다. 객체 수만큼 별도의 사건이나 비용이 있었다고 바꾸지 않는다.

배치는 프로세스의 시간·인과관계를 새로 추정하지 않는다. `layered`의 x 좌표는 읽기 위한 층이고, timestamp 축은 관측 시각이며, execution lane의 순서는 계산 결과가 제공한 선행관계다. 순서가 해결되지 않은 tie를 화면 편의를 위해 임의의 전체 순서로 바꾸지 않는다.

`build_visualization(a, b)`는 두 결과를 독립된 panel들로 묶는다. 두 자료가 같은 모집단이라는 주장이나 암묵적인 join은 하지 않는다. PN/OCPN 주석은 `build_model_visualization(..., annotations=..., metric=...)`, variant의 duration 결합은 `build_variant_duration(statistics, performance)`로 별도 요청한다. 이 경로는 model digest, source, classifier 또는 대상 case의 일치를 검사한다.

각 출처의 `panel_ids`는 그 출처가 설명하는 panel들을, `input_path`는 합성 문서 안의 입력 위치를 기록한다. 중첩 문서를 합치면 panel ID와 출처 참조를 함께 변경하고 입력 경로를 보존한다. 예를 들어 `(1, 0)`은 두 번째 입력 안의 첫 번째 입력이다. 기존 `VisualizationDocument` 하나만 전달하면 이 연결을 그대로 유지하며, 명시한 제목만 바꿀 수 있다. 두 필드가 모두 비어 있는 legacy/custom 출처만 문서 전체에 적용된다. `panel_ids`는 비어 있지만 `input_path`가 있으면 실패한 입력처럼 **연결된 panel이 없는 출처**다. Inspector는 현재 panel에 적용되는 출처만 보여주며, JSON과 SVG metadata에는 전체 출처 목록과 scope를 보존한다.

발견·변환 결과는 알려진 native 결과형을 명시적으로 연결한다. Split·Alpha·POWL·Region·Genetic·OCPN 발견, BPMN/DFG/tree/WF 변환, 모델 축소·분해·OC enhancement 등의 모델과 부가 근거를 함께 보여준다. 임의 객체에 `model` 필드가 있다는 이유로 수용하지 않으며, 결과에 기록된 soundness·equivalence 보증을 화면이 새로 증명한 것으로 표시하지 않는다.

## Case-centric 대체표

**구현**은 아래에 적힌 PIX 자료형·계산 profile을 화면에 연결하는 어댑터와 의미 보존 테스트가 있다는 뜻이다. **부분**은 해당 연결은 있으나 참조 family의 알려진 표현·옵션 범위가 남아 있다는 뜻이다. 두 표기 모두 upstream runtime의 결과·좌표·스타일·모든 옵션과 동등하다는 인증은 아니다. 증거 열은 검증 코드를 가리키며 최종 실행 횟수와 별개다.

| ID | 참조 시각화 | 현재 PIX 연결·표현 | 상태 및 남는 범위 | 증거 |
|---|---|---|---|---|
| V-CC-01 | DFG frequency / performance / cost / timeline | `CaseRelationGraph`의 활동·경로·case·start/end 빈도. 성능 결과는 단위·표본 근거를 갖는 별도 chart/table | **부분**. cost overlay, upstream timeline 배치, 임의 성능 통계를 DFG에 붙이는 API까지 포괄하지 않음 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-02 | PN 및 replay/alignment decoration | place·silent·전이 ID·marking·weight. 검증된 replay/alignment의 발화·삽입·소비·생산·move 계수를 명시적으로 부착 | **부분**. greedy decoration, PN의 임의 performance decoration을 재현하지 않음. label만 같은 다른 전이를 합치지 않음 | [모델](../../tests/viewer/test_visual_model_adapters.py), [주석](../../tests/viewer/test_visual_annotations.py) |
| V-CC-03 | Process tree | operator·leaf occurrence·child 순서·loop do/redo·tau를 그래프와 근거로 표현 | **부분**. 모델에 없는 node frequency를 만들지 않음. upstream symbolic/frequency 표현 전체가 아님 | [모델 테스트](../../tests/viewer/test_visual_model_adapters.py) |
| V-CC-04 | BPMN | PIX `SplitBPMN`의 start/end/task, XOR·parallel gateway, flow ID와 방향 | **부분**. pool, message flow, boundary event 등 native 모델 밖의 BPMN 개념과 upstream 세 배치 방식은 포함하지 않음 | [모델 테스트](../../tests/viewer/test_visual_model_adapters.py) |
| V-CC-05 | POWL BASIC / NET | activity·tau·XOR·loop·partial-order의 containment와 실제 precedence를 별도 관계로 표현 | **부분**. 동일 label의 occurrence는 보존하지만 BASIC/NET의 notation·layout 동등성은 주장하지 않음 | [모델 테스트](../../tests/viewer/test_visual_model_adapters.py) |
| V-CC-06 | Heuristics net | 선택된 dependency graph와 AND binding 대안, pair·loop·frequency·제외 근거를 별도 노드/표로 표현 | **구현 — native profile**. 단순 DFG로 축소하지 않으며 pydotplus의 스타일·배치 복제는 범위 밖 | [모델 테스트](../../tests/viewer/test_visual_model_adapters.py) |
| V-CC-07 | Transition system | state ID/context, activity transition, visits, initial/final count, loop | **구현 — native profile**. 같은 표시 이름의 다른 state는 분리 | [모델 테스트](../../tests/viewer/test_visual_model_adapters.py) |
| V-CC-08 | Prefix tree / trie | native `TransitionSystem`으로 표현한 prefix tree. outgoing edge와 별개인 terminal count 보존 | **구현 — native profile**. upstream trie 객체를 직접 받는 호환 어댑터는 아님 | [모델 테스트](../../tests/viewer/test_visual_model_adapters.py) |
| V-CC-09 | Alignment table | sync/log/model/silent move의 양쪽 활동·event·전이/leaf path, cost, optimal·limited·approximate 상태. native PN/tree/search/DFG/sequence 계열 | **구현 — 지원 결과형**. 임의 upstream alignment 배열과 모든 native 결과 wrapper의 자동 수용은 보장하지 않음 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-10 | Footprints single / comparison / symmetric | 단일 matrix, 활동 합집합의 방향별 또는 대칭 비교. 부분 모델의 미관측 관계와 없는 관계 구분 | **구현 — native profile**. `symmetric=False`는 방향성 있는 포함 비교이며 역방향 차이와 같지 않음 | [모델](../../tests/viewer/test_visual_model_adapters.py), [주석](../../tests/viewer/test_visual_annotations.py) |
| V-CC-11 | SNA | resource ID·방향·signed/unknown weight·정규화·분모를 보존한 network | **구현 — native profile**. NetworkX/PyVis 객체·조작 API 호환은 범위 밖 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-12 | Attribute network | attribute 노드와 parallel relation, 빈도·timed sample 수·기간을 구분 | **구현 — native profile**. 계산 결과의 business-time 설정을 화면이 다시 계산하지 않음 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-13 | 일반 directed graph | `GraphPanel`의 명시적 node/edge ID·종류·방향·metric. self-loop·평행 간선·고립 노드 | **구현 — PIX 입력 계약**. NetworkX 런타임 타입에 대한 drop-in 호환 아님 | [계약](../../tests/viewer/test_visual_contracts.py), [geometry](../../tests/viewer/test_native_geometry.cjs) |
| V-CC-14 | Decision tree | native split feature·비교 연산·threshold·class/training count·leaf prediction·상태 | **구현 — native profile**. sklearn estimator를 받거나 export_graphviz를 실행하지 않음 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-15 | Dotted chart | `CaseLog`의 case lane과 관측 event timestamp. tie·빈 case·missing/naive timestamp를 드러냄 | **부분**. 임의 attribute 축·색 조합·relative-time 선택을 가진 범용 dotted-chart 설정 API는 아님 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-16 | Performance spectrum | 선택 활동의 timestamp를 같은 case/sequence polyline으로 연결하고 개별 표본 유지 | **구현 — native profile**. 빈도 bar로 바꾸지 않으며 upstream 색·샘플링 옵션 전체 복제는 아님 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |
| V-CC-17 | 통계 plot / semilog-x | bar·line·scatter; 제공된 duration·attribute·KDE·calendar-bin 결과와 단위·unknown 유지 | **부분**. log-x 축은 현재 chart 계약에 없음. KDE 등 분석은 기존 계산 결과를 받고 renderer에서 실행하지 않음 | [CC](../../tests/viewer/test_visual_case_adapters.py), [계약](../../tests/viewer/test_visual_contracts.py) |
| V-CC-18 | Variant duration path | 통계와 성능의 원본·classifier·case membership을 검증한 결합. 반복 활동 위치·빈 variant·duration 표본 보존 | **부분**. path의 위치 간격은 duration scale이 아님. upstream normalized spacing·top-N 옵션 전체를 재현하지 않음 | [CC 테스트](../../tests/viewer/test_visual_case_adapters.py) |

## Object-centric 대체표

| ID | 참조 시각화 | 현재 PIX 연결·표현 | 상태 및 남는 범위 | 증거 |
|---|---|---|---|---|
| V-OC-01 | OCDFG classic / ELK | type별 parallel edge, distinct event pair·object·occurrence 세 계수, start/end와 qualifier witness | **부분**. native 빈도 표현은 구현. 임의 성능 지표를 OCDFG에 덧붙이는 UI와 참조 배치 옵션 전체는 아님 | [OC 테스트](../../tests/viewer/test_visual_object_adapters.py) |
| V-OC-02 | OCPN / OPERA annotations | typed place, shared transition, marking, 고정·가변 cardinality. replay 근거로 연결된 Enhanced 모델의 timed-token metric을 부착 | **부분**. 지원 mean metric과 native replay profile에 한정. Brachmann 배치·OCPA별 notation·모든 decoration variant 동등성은 미검증 | [모델](../../tests/viewer/test_visual_model_adapters.py), [주석](../../tests/viewer/test_visual_annotations.py) |
| V-OC-03 | Object graph | 객체 ID/type, interaction·descendant·inheritance·cobirth·codeath 등 native 관계·방향·witness | **구현 — 지원 native 관계**. instance graph와 object-type graph를 분리 | [OC 테스트](../../tests/viewer/test_visual_object_adapters.py) |
| V-OC-04 | Event/activity ↔ object type | activity/type 이분 그래프, 선택 qualifier와 frequency의 평가 단위. OTG는 별도 type relation graph | **구현 — native profile**. 같은 이름의 activity와 object type을 별도 ID로 유지 | [OC 테스트](../../tests/viewer/test_visual_object_adapters.py) |
| V-OC-05 | Interleavings | witness에 포함된 양쪽 process 구간과 cross-process link, source side·event/case ID·time unit. OCEL 변환 결과에서는 원본 qualifier 유지 | **부분**. 두 source의 전체 DFG와 집계 cross-edge를 함께 그리는 overlay는 아님. 원본 전체가 없는 witness를 완전한 DFG라고 표시하지 않음 | [OC 테스트](../../tests/viewer/test_visual_object_adapters.py) |
| V-OC-06 | Constraint graph | activity/object/formula 종류별 노드, cf/obj/perf 및 native graph predicates, comparator·threshold·평가 상태 | **구현 — 명시된 native 제약**. unknown을 pass/fail로 바꾸지 않음. 데이터에서 constraint graph를 자동 발견하는 기능과 별개 | [OC 테스트](../../tests/viewer/test_visual_object_adapters.py) |
| V-OC-07 | OC chevron / execution lanes / variant layout | `build_variant_visualization`이 일치하는 execution·variant 결과를 결합하여 대표 실행의 객체 instance lane과 shared-event chevron, 빈도·모집단·구성 실행 근거를 표현. raw helper는 한 execution을 명시적으로 입력 | **구현 — 2026-09-16 native profile**. PIX exact qualified-incidence 동치 정의를 유지하며 OCPA 기본 근사 variant와 동일하다고 주장하지 않음. 같은 event의 모든 lane 표시가 같은 inclusive 슬롯을 참조. 미해결 순서나 객체 없는 사건은 임의로 보완하지 않음 | [변경 요구사항·인수 기준](2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md), [이번 검증](../version/2026-09-16_GRAPHVIZ_CHEVRON_VALIDATION.md), [전용 테스트](../../tests/viewer/test_visual_chevrons.py) |
| V-OC-08 | OC alignment | 공동 move의 log/model 활동·binding 객체·상태·비용과 객체 lane 표시, limited 결과의 null 비용 | **구현 — native joint alignment**. 공동 move 비용을 객체 수만큼 복제하지 않음. upstream matplotlib 모양과 동등성은 미검증 | [OC 테스트](../../tests/viewer/test_visual_object_adapters.py) |

## PIX 모델과 계산 때문에 추가한 표현

아래는 두 고정 참조 라이브러리의 독립 visualization family를 모두 옮겼다는 근거로 합산하지 않는다.

| 표현 | 도메인 의미 |
|---|---|
| OCCN | causal channel과 AND binding 대안, same/disjoint object-set 제약, cardinality, 빈 binding·외부 경계 |
| SAW-net | arc cardinality histogram의 분모·관측 witness 및 공동 fitting witness. 서로 독립인 확률로 바꾸지 않음 |
| Data Petri net | 원 PN과 decision guard, 학습 출처, 조건식과 미학습/unknown 상태 |
| Declare / log skeleton / temporal profile | 제약의 방향·활성화 분모·frequency와 시간 평균/편차·단위의 표·그래프 |
| OC raw log / performance / temporal summary / cube | 시간에 따른 속성의 선언 type, E2O qualifier, event/object/참여 행의 다른 모집단과 known/unknown 표본. cube panel은 type 변경 계획의 근거이며 일반 다차원 event-count cube 화면은 아님 |

## 검증과 저장 경계

테스트는 그림이 생성되었다는 사실 외에 의미를 확인한다. 동일 label의 다른 ID, 반복 활동, silent transition, self-loop·parallel edge, 빈 데이터, 악의적인 HTML 모양의 label, 큰 정수, null/unknown/partial, 변조된 계산 출처, 잘못 결합한 성능 표본을 다룬다. OC에서는 shared event·qualifier 다중성·관계의 방향·미해결 tie·공동 alignment 비용을 별도 사례로 검사한다.

실행 대상은 [viewer Python 테스트](../../tests/viewer), [geometry 테스트](../../tests/viewer/test_native_geometry.cjs), [UI 테스트](../../tests/viewer/test_visualization_ui.cjs), 실제 브라우저 테스트 및 [재현용 gallery](../../examples/native_visualization_demo.py)다. 이 문서의 행별 증거는 **테스트의 존재와 검사 내용**이며, 작성 도중 일부 실행 결과를 합산한 최종 통과 수가 아니다. 최종 실행 결과·브라우저 캡처·패키지 검사는 해당 검증 산출물과 함께 판정해야 한다.

HTML과 시각화 JSON에는 제공된 전체 view data가 들어간다. 화면 검색·페이지화·표시 한도는 데이터 삭제나 비식별화가 아니다. SVG 저장은 현재 선택한 그리기 panel을 내보내는 기능이며, Python에서 PNG/PDF를 생성하는 API는 현재 지원으로 기록하지 않는다.

native 시각화 JSON은 정수 값을 보존한다. HTML로 넘길 때는 JavaScript가 정수로 정확히 표현할 수 없는 절댓값 `2**53 - 1` 초과 수를 거부한다. 정밀도가 사라진 숫자를 정상 관측값처럼 보여주지 않기 위한 경계다. 화면의 축·요약 label은 읽기 위해 반올림될 수 있으므로 원값은 inspector와 JSON에서 확인한다.

## 판정의 유효 범위와 재검토 조건

이 문서는 위 두 참조 버전과 작성 시점의 PIX 소스에 유효하다. upstream 버전, native 모델/result schema, adapter 또는 geometry가 바뀌면 해당 행을 다시 확인한다. source hash 색인은 참조 범위를 고정하며, 현재 코드를 고정시키는 영구 보증은 아니다.

다음 반례가 확인되면 해당 구현의 의미 보존 판정을 철회한다: 같은 사건/전이를 서로 다른 것으로 복제하거나 다른 ID를 합치는 경우, 미관측 값을 0·적합·확정 순서로 만드는 경우, model/source가 다른 주석을 승인하는 경우, 비용·분모·단위가 표시 과정에서 바뀌는 경우. 사용 가능한 화면 품질의 판단은 실제 업무 데이터로 topology와 근거를 읽고 선택할 수 있는지를 확인한 범위에 한정하며, 미측정 크기의 처리량은 알 수 없음이다.

현재 구조 선택은 **PIX가 도메인 어댑터·문서·SVG 화면·chevron 의미를 소유하고 Graphviz를 graph 기본 배치로 사용하는 방식**이다. 자체 배치와 ELK는 명시적 대안이며, 대체 범위는 위 26행의 지원 profile과 잔여 항목으로 판단한다.
