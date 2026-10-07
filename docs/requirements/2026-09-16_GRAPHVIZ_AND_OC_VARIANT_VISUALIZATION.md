# PIX Graphviz 기본 배치와 OC variant chevron 요구사항

작성일: **2026-09-16**. 상태: **사용자 결정 반영, 구현·통합·독립 설치 검증 통과**. 실제 화면의 사용자 수용 판단은 별도다.

변경 전후 샘플, 전용 Chromium 검사와 최종 전체 검사 결과는 [검증 기록](../version/2026-09-16_GRAPHVIZ_CHEVRON_VALIDATION.md)에 있다. 자동 검사 통과를 모든 실무 graph의 가독성이나 upstream 전체 동등성 승인으로 해석하지 않는다.

사용자는 DFG·OCDFG 샘플을 검토한 뒤 Graphviz를 기본으로 사용하도록 요구했으며, OCPA의 *Variant Calculation and Layouting* 표현을 PIX에 포함하도록 요구했다. 이 문서는 그 결정을 도메인 의미·실행 경로·인수 조건으로 기록한다. [기존 시각화 합집합](2026-09-15_PIX_VISUALIZATION_UNION.md), [개발 계획](2026-09-13_PIX_DETAILED_DEVELOPMENT_PLAN.md)의 배치 결정과 충돌하면 본 문서가 우선한다. 기존 PM4Py/OCPA scope 원본과 2026-09-15 테스트 결과는 역사 기록으로 보존한다.

## 변경 근거와 적용 범위

확인한 사실은 PIX 자체 배치로 생성한 DFG 2개와 OCDFG 2개의 샘플에서 간선 통로와 라벨이 겹쳐 연결 관계를 읽기 어려웠다는 것이다. 해당 입력은 합성 로그이며 모든 실무 그래프에 대한 성능 실험은 아니다. [변경 전 샘플](../../.artifacts/graph-quality-2026-09-16/index.html)

채택한 조치는 **Graphviz를 신규·기존 모든 graph의 기본 배치로 사용**하고, PIX가 계산·도메인 표현·SVG 화면·근거 조회를 유지하는 것이다. 자체 배치를 그대로 기본으로 두는 대안은 위 샘플과 사용자 지시 때문에 채택하지 않았다. Graphviz가 모든 그래프에서 더 좋은 결과를 보장한다는 주장은 하지 않는다. 같은 입력의 변경 전후 그림으로 품질을 검토한다.

| 대상 | 기본값 | 명시적 대안 | 미지원 조합 |
|---|---|---|---|
| `VisualizationDocument`의 `GraphPanel` | Graphviz | PIX native 실험 배치 | ELK |
| 기존 `GraphDocument` | Graphviz | 기존 ELK | PIX native |
| 기존 `ModelGraphDocument` | Graphviz | 기존 ELK | PIX native |
| Matrix / chart / timeline / table | 해당 panel의 PIX renderer | 해당 없음 | graph 배치 설정으로 축 의미를 바꾸지 않음 |
| 신규 `ChevronPanel` | 선행관계 슬롯을 그리는 PIX renderer | 해당 없음 | graph 배치로 순서·슬롯을 재해석하지 않음 |

`render_html`, `export_html`, `export_html_report`는 `layout_engine="graphviz"`를 기본으로 받는다. `"native"`와 `"elk"`는 위 조합에서만 허용한다. 지원하지 않는 조합은 거부한다. 실행 실패나 geometry 검증 실패는 표시하고, 다른 엔진으로 조용히 전환하지 않는다.

## Graphviz를 포함하는 방식

Graphviz **16.0.0**을 공식 `@viz-js/viz` **3.30.0**의 JavaScript·WebAssembly 배포물을 통해 사용한다. Vendor 파일을 PIX wheel에 넣고 HTML export에도 필요한 실행 자산을 넣는다. 사용자는 시스템 `dot`, Python `graphviz`, Node 또는 시각화 서버를 따로 설치할 필요가 없다. HTML은 CDN이나 원격 서버에 graph 데이터를 보내지 않고 브라우저에서 배치한다. Graphviz 의존성 자체는 존재하며 판본·라이선스·무결성 정보를 기록한다. [Viz.js 공식 API](https://viz-js.com/api/)

고정 정보는 [Graphviz provenance](../../src/pix/viewer/assets/vendor/graphviz-provenance.json)에 있다. Viz.js MIT, Graphviz EPL-2.0, Expat MIT 고지를 각각 동봉한다. Registry archive 무결성·배포 파일 hash의 확인은 source에서 같은 binary를 재빌드했다는 검증과 다르며, source-build 재현성은 현재 미검증이다.

| 역할 | 담당 | 보존 조건 |
|---|---|---|
| DFG/OCDFG·발견·conformance·variant 계산 | PIX 계산 모듈 | PM4Py/OCPA/Graphviz에 계산 위임하지 않음 |
| 계산 결과를 표시 자료로 연결 | PIX adapter·시각화 계약 | event/object/model ID, 단위, 빈도, qualifier, 출처·partial 상태 보존 |
| Graph node 위치·spline·label 좌표 | Graphviz | 평행 간선·자기 루프·ID를 제거하거나 합치지 않음 |
| 색·도형·선택·검색·확대·근거 조회 | PIX SVG/UI | 모델 표기와 관측 빈도의 의미를 구별 |
| HTML·JSON·SVG 출력 | PIX exporter | 선택한 엔진의 고지, 표시 자료·출처·범위 보존 |

기존 OCDFG의 type filter와 event-pair/object/occurrence 계수 선택도 유지한다. 필터는 계산 결과를 다시 계산하거나 숨긴 객체를 삭제하지 않는다. PN/OCPN에서는 transition identity·silent 표시·marking·weight/cardinality를 유지한다. Graphviz의 graph layout은 soundness나 병목을 계산한 결과가 아니다.

## OCPA에서 가져오는 의미

OCPA 공식 문서는 **variant 계산**과 **chevron 좌표 배치**를 구분한다. Variant 계산에는 근사 표현과 동형성 검사가 있으며 기본 설정은 근사다. Chevron 배치는 좌표를 반환하고 실제 화면은 별도 도구가 그리는 구조로 설명한다. PIX는 이 객체별 공유 사건 표현을 자신의 계산 결과와 UI에 연결한다. OCPA 런타임에 의존하거나 upstream의 화면 전체를 복제하지 않는다. [OCPA 공식 discovery 문서](https://ocpa.readthedocs.io/en/latest/discovery.html)

PIX의 기존 variant는 **qualified event–object incidence에 대한 exact 정의와 명시된 탐색 한도**를 갖는다. 이를 OCPA의 기본 근사 분류로 바꾸지 않는다. 따라서 PIX와 OCPA의 variant 수·대표 실행이 같다고 주장하지 않는다. 이번 요구의 핵심은 계산 정의의 이름 통일이 아니라, PIX가 계산한 variant를 객체 참여와 공유 사건이 읽히는 형태로 보여주는 것이다.

### 도메인에서 읽는 방법

행 하나는 객체형 전체가 아니라 **개별 객체 instance**다. 예를 들어 주문 1개와 상품 2개가 있으면 `Order:1`, `Item:1`, `Item:2`의 세 행을 갖는다. 색은 객체형을 나타내며, 라벨만 같은 객체도 ID가 다르면 합치지 않는다.

사건은 한 번만 정의한다. `Pack` 사건에 위 세 객체가 같이 참여했다면 세 행에 같은 위치의 chevron을 표시하되 원 event ID는 하나다. 선택한 표시에서 동일한 사건과 참여 객체·qualifier 근거를 확인한다. 화면에 세 번 보였다는 이유로 사건 수·빈도·비용을 세 배로 만들지 않는다.

가로축은 **precedence slot**이다. 관측 시각이나 duration이 아니다. 사건의 시작은 선행관계 DAG에서 계산한 가장 긴 경로의 단계이며, 끝은 가장 먼저 시작하는 후속 사건의 직전 단계다. 후속 사건이 없는 sink의 끝은 자신의 시작과 같다. 양끝을 포함하는 슬롯이므로 `[2, 2]`도 한 칸이다.

| 예제 | 선행관계 | 표시 슬롯 | 읽는 의미 |
|---|---|---|---|
| 순차 | A → B → C | A `[0,0]`, B `[1,1]`, C `[2,2]` | 세 단계의 순서 |
| 짧고 긴 분기의 합류 | A → B → D, A → C → E → D | A `[0,0]`, B `[1,2]`, C `[1,1]`, E `[2,2]`, D `[3,3]` | B는 합류 전까지 넓게 표시되지만 2단위 시간 동안 실행했다는 뜻은 아님 |
| 공유 사건 | Order와 Item 모두의 후속 사건이 Pack | Pack은 모든 참여 행에서 같은 `[start,end]` | 하나의 사건에 여러 객체가 참여 |
| 독립 사건 | 두 사건 사이에 경로 없음 | 같은 시작 슬롯에 놓일 수 있음 | 임의의 전체 순서를 부여하지 않음 |

행을 보기 좋게 정렬하는 것과 선행관계를 추가하는 것은 구분한다. 미해결 timestamp tie를 렌더링 편의상 순서로 바꾸지 않는다. 순환 관계나 충분한 참여 근거가 없는 입력을 정상 chevron으로 꾸미지 않는다. 객체 없는 사건에는 임의의 가상 객체를 만들지 않는다.

### 공개 경로와 자료 계약

| API / 계약 | 역할 |
|---|---|
| `build_variant_visualization(execution_result, variant_result, *, title=None)` | 원본·parent execution 계산·membership가 맞는 결과를 검증하고 대표 variant chevron과 근거를 문서로 묶음 |
| `build_execution_chevrons(execution, *, title=None, panel_id=None)` | 한 execution을 `ChevronPanel`로 연결하는 저수준 helper |
| `ChevronLane(id, label, object_type, object_id, details=())` | 객체 instance의 행과 객체형·근거 |
| `ChevronEvent(id, label, start, end, lane_ids, details=())` | 한 사건의 원 ID, inclusive 정수 슬롯, 여러 참여 행 |
| `ChevronPanel(id, title, lanes=(), events=(), variant_id=None, frequency=None, population=None, description="")` | 한 대표 실행의 chevron과 variant 빈도·모집단 |

Source digest만 같다고 결과를 결합하지 않는다. Variant가 어느 execution 계산의 결과인지 parent 연결을 확인하고, 모든 execution ID가 partition에 정확히 한 번 포함되는지, member 목록·대표 실행·빈도·모집단이 맞는지 확인한다. 다른 선택 조건으로 추출한 execution, 누락·중복·존재하지 않는 대표 실행은 거부한다. 대표 그림만 남기고 구성 execution의 근거를 잃지 않는다.

현재 variant helper는 **`COMPUTED`인 정확한 `ExecutionSet`과 `VariantSet`만** 받는다. Partial·실패 결과, 미해결 tie, 불완전한 객체 경로, 전역 cycle은 `ValueError`로 거부한다. 명시적으로 event ID로 해결한 동률은 허용하고 설명과 order-evidence의 `tie_broken`으로 공개한다. Canonical labeling을 다시 실행하지 않으므로 payload 그룹핑에 대한 동형성을 재증명하는 검증기는 아니다.

추출 요청과 근거가 맞는지도 검사한다. Selected/excluded incidence의 객체형·qualifier 선택, in-scope 객체형과 leading role이 원 spec과 다르면 거부한다. 같은 source를 가리킨다는 이유만으로 다른 선택 조건의 근거를 승인하지 않는다.

Raw helper는 객체 없는 사건 또는 경계 객체에만 연결된 사건이 하나라도 있으면 거부한다. Variant 문서에서는 해당 대표 실행의 chevron에 임의의 lane을 추가하지 않고 `variant-unlaned-events` 표에 event ID·활동·timestamp·이유를 보존한다. 빈 로그는 빈 빈도·근거 표, 사건 없는 leading-object 실행은 비어 있는 객체 lane으로 표시한다. 구현과 의미 검증은 [chevron builder](../../src/pix/viewer/visual_chevrons.py)와 [전용 테스트](../../tests/viewer/test_visual_chevrons.py)에 있다.

## 인수 조건

아래는 구현 완료 판정에 필요한 검사 목록이다. 테스트 파일이 존재하는 것, 실제 테스트가 통과한 것, 사람이 그림을 읽을 수 있다고 판단한 것은 별도로 기록한다.

| ID | 조건 | 검증 내용 |
|---|---|---|
| GV-01 | 모든 graph의 기본값 | 신규 graph, 기존 DFG/OCDFG, 기존 PN/OCPN을 옵션 없이 export했을 때 실제 Graphviz 실행 |
| GV-02 | 명시적 대안·실패 | native/ELK 허용 조합과 거부 조합, 초기화·배치 실패의 표시, 자동 fallback 없음 |
| GV-03 | 관계·표현 보존 | 동일 label의 다른 ID, 평행·양방향 간선, 자기 루프, 객체형, marking, weight/cardinality, 빈 graph, 긴·Unicode label |
| GV-04 | 품질의 직접 검토 | 기존 DFG 2개·OCDFG 2개와 동일한 입력·계수로 새 HTML·PNG 생성. edge 경로·label·화살표·객체형 읽기, 선택·zoom·SVG 확인 |
| GV-05 | 배포·오프라인 | 판본·원본 archive·license·SHA-256 고정, wheel의 vendor 포함, 독립 설치본 HTML에서 네트워크 없이 실제 브라우저 실행 |
| CV-01 | 슬롯의 독립 검산 | 순차, 분기·합류, 길이 다른 분기, sink, 분리된 부분 순서의 기대 슬롯. 음수·역전·순환·미해결 순서를 조용히 보완하지 않음 |
| CV-02 | 공유 사건·참여 | 같은 event를 여러 lane에 표시해도 한 ID와 같은 시작·끝. qualifier 다중성으로 참여 행이나 사건 수가 증가하지 않음 |
| CV-03 | Variant 결합 | 원본·parent computation·대표 실행·membership·빈도·모집단 검증. 다른 execution 선택, 변조된 근거, partial/unclassified 사례 |
| CV-04 | 계약·저장 | Chevron JSON 왕복, 잘못된 참조·중복 ID·숫자 타입·큰 정수 경계, HTML escaping, SVG의 원본 출처·선택 범위 |
| CV-05 | 실제 화면 | 객체형별 색·instance lane·shared-event 정렬·순서 축 설명, 긴 label, 빈/부분/표현 불가 상태, 선택·검색·SVG 출력 |

기존 계산·import·시각화 테스트도 회귀 검사한다. 수치화하지 않은 시각 품질을 임의의 점수나 개선율로 만들지 않는다. 대형 실무 OCEL의 최대 처리 규모·지연·메모리와 타 라이브러리 대비 우위는 **알 수 없음**이며 별도 측정 대상이다.

## 실행 기록과 판정 범위

최종 통합 실행은 pytest 8,883개와 subtest 1,169개 통과·27개 skip, JavaScript 223개 통과를 기록했다. 실제 Chromium 21개는 pytest 통과 수에 포함된다. 명령·환경·source snapshot·HTML/PNG와 독립 wheel 검증 범위는 [이번 검증 기록](../version/2026-09-16_GRAPHVIZ_CHEVRON_VALIDATION.md)에서 구별한다. [2026-09-15 검증](../version/2026-09-15_NATIVE_VISUALIZATION_VALIDATION.md)은 변경 전 기준선이며 새 변경 통과 수로 합산하지 않는다.

이 요구는 2026-09-16 사용자 지시와 위 pinned 버전에 유효하다. Graphviz vendor·계약·실행기·variant 정의가 바뀌면 영향을 받는 검사를 다시 한다. ID·참여·빈도·단위·출처가 바뀌거나 shared-event 슬롯이 서로 달라지는 반례가 나오면 해당 의미 보존 판단을 철회한다. 실제 graph에서 심한 겹침·지연이 남으면 Graphviz라는 이름 자체를 품질 근거로 삼지 않고 설정·표현·배치를 재검토한다.

최종 구조 결정은 **Graphviz를 graph의 기본 배치로 사용하고, PIX는 계산 의미·SVG 상호작용·객체 중심 variant chevron을 소유하는 것**이다.
