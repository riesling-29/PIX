# PIX 시각화 사용 가이드

2026-09-15까지의 테스트·브라우저·설치 검사는 [당시 통합 검증 기록](../version/2026-09-15_NATIVE_VISUALIZATION_VALIDATION.md)에 있다. 아래 기본 배치와 chevron은 2026-09-16 변경이며, [변경 요구사항](../requirements/2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md)의 별도 인수 검사를 따른다. [이번 검증 기록과 비교 화면](../version/2026-09-16_GRAPHVIZ_CHEVRON_VALIDATION.md)에서 실제 검사 범위를 확인한다.

PIX의 계산 결과·모델·로그를 `pix.viewer.build_visualization`으로 묶으면, 브라우저에서 직접 열 수 있는 오프라인 HTML을 만들 수 있다. **모든 graph의 기본 배치는 Graphviz이고 SVG 화면과 상호작용은 PIX가 담당한다.** Graphviz 16.0.0을 `@viz-js/viz` 3.30.0의 WebAssembly와 함께 HTML에 넣으므로, 사용자는 `dot`이나 Python `graphviz`, Node를 별도로 설치할 필요가 없다. CDN과 시각화 서버도 필요하지 않다. 개발 단계의 JavaScript 테스트에 Node를 쓰는 것과 사용자의 HTML 실행은 별개다.

이 가이드는 **2026-09-16 변경을 포함한 시각화 경로**에 해당한다. PM4Py/OCPA의 입력 객체나 모든 시각화 옵션을 그대로 받는 API는 아니다. 참조별 지원 범위와 남은 기능은 [시각화 합집합 문서](../requirements/2026-09-15_PIX_VISUALIZATION_UNION.md)에 정리했다.

## 먼저 실제 예제를 보기

저장소에서 다음 예제를 실행하면 CC/OC 로그를 직접 구성하고, PIX 계산을 거친 결과로 gallery를 만든다.

```powershell
python examples/native_visualization_demo.py --output .artifacts/visualization-demo
```

생성된 `.artifacts/visualization-demo/index.html`을 브라우저로 연다. 이미 같은 이름의 산출물이 있으면 기본적으로 덮어쓰지 않는다. 의도적으로 갱신할 때는 예제의 `--overwrite` 옵션을 사용한다.

[예제 소스](../../examples/native_visualization_demo.py)는 관측 flow, process models, alignment/replay, footprints, 시간·duration, 제약, OCDFG, OCPN/SAW, raw OCEL을 만든다. 계산 입력은 합성 데이터다. 별도의 `rendering-fixture` 페이지에 있는 수치는 renderer 검사용으로 공급한 값이며, 분석에서 발견한 결과로 표시하지 않는다.

## 계산 결과를 화면으로 연결하기

다음 예제에서 `log`는 import가 끝난 PIX `CaseLog`다. 계산 결과를 그대로 넘기면 계산 ID, source digest, 요청 조건과 상태를 화면에서 추적할 수 있다.

```python
from pix import case_centric as cc
from pix.viewer import build_visualization, export_html, write_visualization

dfg = cc.discover_dfg(log)
performance = cc.statistics.measure_case_performance(log)

view = build_visualization(dfg, performance, title="Case flow and duration")
export_html(view, "case-analysis.html")
write_visualization(view, "case-analysis.visualization.json")
```

DFG와 성능은 한 문서의 독립 panel들이다. 이 호출이 성능 숫자를 임의로 DFG edge에 붙이거나 서로 다른 계산 모집단을 결합하지는 않는다. `result.value`만 넘기는 대신 원 `ComputationResult`를 넘기면 계산 출처와 부분 결과 상태를 함께 보존할 수 있다.

출처의 `Associated panel IDs`는 연결된 panel, `Input path`는 입력 위치다. `[1, 0]`은 두 번째 입력 안의 첫 번째 입력을 뜻한다. 문서를 중첩해서 묶어도 이 연결을 유지하며, Inspector에는 현재 panel에 적용되는 출처만 나온다. 두 필드가 모두 비어 있는 기존/custom 출처는 문서 전체에 적용된다. 입력 경로는 있지만 panel 목록이 비어 있으면 패널을 만들지 못한 입력의 출처이며, 다른 panel의 계산 근거로 표시하지 않는다. 기존 시각화 문서 하나만 다시 전달하면 출처 연결은 바뀌지 않는다.

OCEL에서도 같은 진입점을 쓴다. 아래 `ocel`은 PIX canonical OCEL이고, 객체 type은 해당 로그에 실제로 선언된 이름을 선택한다.

```python
from pix import object_centric as oc
from pix.contracts.analysis import OCDFGSpec
from pix.viewer import build_visualization, export_html

ocdfg = oc.discover_ocdfg(ocel, OCDFGSpec(("order", "parcel")))
view = build_visualization(ocdfg, ocel, title="Objects and shared events")
export_html(view, "object-analysis.html")
```

모델 객체 자체도 입력할 수 있다. `ModelArtifact`를 갖고 있다면 원 모델만 떼어 내기보다 artifact를 전달해야 발견·변환의 출처가 유지된다. 지원하지 않는 객체는 `UnsupportedVisualizationError`로 거부한다. 값을 임의의 문자열 표로 바꿔 지원되는 것처럼 보이지 않는다.

## 화면에서 판단할 내용

| Panel | 도메인에서 읽는 내용 | 주의해서 구분할 의미 |
|---|---|---|
| Graph | 모델 구조, 관계, 전이·객체·사건과 연결 근거 | 그림의 거리·간선 폭이 시간·빈도를 뜻하지 않음. 선택한 항목의 metric과 단위를 확인 |
| Matrix | footprints, 관계 비교, cube 등의 행·열 관계 | `?`는 unknown, `—`는 공급되지 않은 cell. `0`은 실제로 공급된 수치 0 |
| Chart | 제공된 빈도·duration·분포·timestamp 경로 | 축의 이름·단위, 알려진 표본 수, 결측을 확인. renderer가 KDE나 통계를 새로 계산하지 않음 |
| Timeline | case 또는 object lane의 사건·구간 | timestamp인지 relative/선행관계 위치인지 확인. 끝이 없는 구간은 종료 시각이 알려지지 않은 상태 |
| Chevron | 대표 OC execution의 객체별 활동과 공유 사건 | lane은 객체 instance. 같은 event의 여러 표시가 하나의 사건을 참조하며, 가로 슬롯과 화살표 폭은 실제 시간이 아님 |
| Table | move·binding·token·qualifier·표본·계산 조건 | 화면 행 수와 원본 행 수는 다를 수 있음. 검색·페이지화가 계산 결과를 바꾸지 않음 |

탭으로 panel을 바꾸고, 항목을 선택하면 오른쪽 inspector에 전체 label·ID·원값·단위·근거가 나온다. 그리기 panel은 drag로 이동하고 scroll 또는 `+`/`−`로 확대·축소하며 `Fit`으로 전체를 맞춘다. `Readable` 또는 키보드 `1`은 SVG 1단위를 화면의 CSS 1픽셀에 맞춘다. 키보드로는 `Tab`으로 항목에 접근하고 `Enter`로 근거를 연다. 검색은 그리기 항목을 강조하고 표에서는 현재 보여줄 행을 고른다.

표시 한도를 넘으면 한도 안내를 보여주고 전체 원자료를 유지한다. 일부 항목을 조용히 버린 뒤 전체를 그렸다고 표시하지 않는다. 기존 기본값은 graph 1,500 nodes / 6,000 edges, matrix 12,000 grid positions, chart 15,000 points, timeline 10,000 items이며, 표는 페이지당 50행이다. 이는 제품의 검증된 최대 처리량이나 속도 보장이 아니라 **기본 표시 한도**다. 실험용 native force 배치에는 별도로 1,000개 node 제한이 있다. 대형 실무 데이터의 적정 한도는 실제 화면으로 확인해야 한다.

CC process tree의 같은 activity가 서로 다른 위치에 나오면 서로 다른 occurrence다. POWL의 자식 포함 관계와 선행관계도 별개다. Heuristics net은 선택 edge만 보면 AND binding 의미가 사라질 수 있으므로 binding 노드와 관련 표를 함께 본다.

OCDFG에서는 `event_pairs`, `objects`, `occurrences`가 각각 다른 수치다. 같은 사건이 두 object type에 참여하거나 같은 event–object 쌍에 qualifier가 여럿 있다고 해서 unique event 수를 늘리지 않는다. 실제 execution의 객체 lane에서 같은 shared event가 여러 lane에 나타나더라도, 그것은 하나의 사건에 대한 여러 참여 표시다. OC alignment의 공동 move 비용도 한 번만 집계한다.

## 모델 위에 계산 근거 붙이기

모델과 분석 결과를 나란히 보는 것과 모델 위에 수치를 붙이는 것은 다르다. 전이별 annotation은 명시적으로 요청한다. 아래 `net`은 `log`에 대해 replay를 실행할 PIX `PetriNet`이다.

```python
from pix import case_centric as cc
from pix.viewer import build_model_visualization, export_html

replay = cc.replay_traces(log, net)
view = build_model_visualization(
    net, annotations=replay, metric="firing_count", title="Recorded transition firings"
)
export_html(view, "replay-annotations.html")
```

지원한 replay metric은 `firing_count`, `inserted_tokens`, `consumed_tokens`, `produced_tokens`다. 지원한 CC alignment metric은 `firing_count`, `synchronous_count`, `model_move_count`, `silent_count`다. 각각 기록된 witness의 계수이며 활동 빈도와 같은 이름으로 바꾸지 않는다. 다른 모델의 결과, 변조된 요청, label만 같은 다른 전이의 witness는 거부한다.

OC timed-token 결과는 `performance:<metric 이름>:mean` 형식으로 명시한다. 실제 전이에 숫자를 붙이려면 전이별 replay 근거를 포함하는 `EnhancedObjectCentricPetriNet` 결과가 필요하다. standalone timed replay는 event에서 transition으로 가는 근거가 충분하지 않으므로 모델 옆에 sample table을 보여주며 전이를 추측해서 칠하지 않는다. 평균은 known sample에 대한 값이고 unknown 수와 정확한 분자·분모를 근거에서 확인할 수 있다.

지원되지 않은 metric을 계산해 만들어 주거나, 탐색 한도로 누락된 전이 횟수를 확정적인 0으로 채우지 않는다. 상세 입력 조건은 [주석 테스트](../../tests/viewer/test_visual_annotations.py)에 사례로 고정되어 있다.

## 명시적으로 두 결과 비교·결합하기

```python
from pix.viewer import compare_footprints, build_variant_duration

comparison = compare_footprints(left_footprints, right_footprints, symmetric=True)
duration_view = build_variant_duration(statistics_result, performance_result)
```

Footprints는 두 결과의 활동 합집합을 축으로 쓴다. `symmetric=False`는 왼쪽 관계에 대한 방향성 있는 비교이고, `True`는 양쪽 차이를 검사한다. 한쪽에 activity가 없거나 bounded exploration이 끝나지 않은 경우를 확정된 관계 부재와 구분한다. 관측 footprints의 `||`는 양방향 직접후속이 관측되었다는 뜻이며, 실제 concurrency를 증명했다는 뜻은 아니다. 모델의 commuting witness와는 근거가 다르다.

Variant–duration 결합은 같은 원본·classifier·case 모집단인지, variant별 실제 case membership과 표본 수가 맞는지 검사한다. path에 같은 활동이 두 번 등장해도 위치를 유지한다. 경로 그림의 간격은 활동 위치이며 실제 flow time의 축척으로 해석하지 않는다.

## Object-centric variant를 chevron으로 보기

OCPA의 *Variant Calculation and Layouting*처럼 객체별 행을 따라 활동을 읽고, 여러 객체가 함께 참여한 사건을 같은 가로 위치에서 확인한다. **Variant를 묶는 계산**과 **그 대표 실행을 그리는 배치**는 별개다. PIX의 기존 exact qualified-incidence variant 정의를 유지하며, OCPA 기본 근사 방식과 variant 수가 같다고 가정하지 않는다. [OCPA 공식 설명](https://ocpa.readthedocs.io/en/latest/discovery.html)

```python
from pix.viewer import build_variant_visualization, export_html

# 같은 원본에서 추출한 execution 결과와, 그 결과로 계산한 variant 결과
view = build_variant_visualization(execution_result, variant_result, title="OC variants")
export_html(view, "object-variants.html")
```

단순히 두 결과의 source digest만 같은 것으로는 충분하지 않다. Variant가 참조한 parent execution 계산과 원본 결과가 맞아야 하며, 모든 execution이 variant partition에 정확히 한 번 포함되는지와 대표 실행·빈도·모집단·출처를 검사한다. 현재 helper는 **`COMPUTED`인 정확한 `ExecutionSet`과 `VariantSet`만** 받는다. Partial·실패 결과, 미해결 tie·불완전한 객체 경로·cycle은 `ValueError`로 거부한다. 명시적으로 event ID로 해결한 tie는 허용하고 순서 근거의 `tie_broken`으로 드러낸다. Canonical labeling을 다시 실행해 variant의 동형성을 재증명하는 기능은 아니다.

행 하나는 `Order` 같은 객체형 전체가 아니라 `Order:42` 같은 **개별 객체**다. 색은 객체형을 구별한다. 같은 사건이 주문·상품·배송 객체에 함께 참여하면 해당 행마다 chevron이 보이지만, 원 event ID와 시작·끝 슬롯은 하나다. 선택한 표시의 ID와 참여 근거를 확인해 같은 사건임을 구별한다.

시작 슬롯은 선행 사건 중 가장 긴 경로의 단계다. 끝 슬롯은 가장 먼저 시작하는 후속 사건의 직전 슬롯이며, 후속 사건이 없으면 자신의 시작 슬롯이다. `[start, end]`는 양끝을 포함하므로 `[2, 2]`도 한 칸을 차지한다. 경로 길이가 다른 분기에서는 짧은 분기의 chevron이 합류 전까지 넓어질 수 있다. **이 폭은 기다린 시간이나 처리시간이 아니다.** 정확한 시간 비교는 timestamp timeline과 성능 계산에서 한다.

한 실행만 직접 그리고 싶으면 `build_execution_chevrons(execution, title=..., panel_id=...)`로 `ChevronPanel`을 만들 수 있다. 이 저수준 helper는 객체 없는 사건 또는 경계 객체에만 연결되어 내부 lane이 없는 사건을 포함하면 거부한다. Variant helper에서는 그러한 사건을 대표 chevron에 억지로 그리지 않고 `variant-unlaned-events` 표에 ID·활동·timestamp·이유를 남긴다. 빈 로그는 빈 빈도·근거 표로, 사건 없는 leading-object 실행은 빈 객체 lane으로 표현한다. Chevron 배치는 Graphviz graph 배치와 독립된 도메인 규칙이다.

## 저장 형식과 다시 열기

| 형식 | 용도 | 보존·제한 |
|---|---|---|
| self-contained HTML | 서버 없이 탐색·공유 | JS/CSS와 제공된 전체 view data 포함. 브라우저 필터는 삭제·비식별화가 아님 |
| 시각화 JSON | view document 저장·복원 | schema `pix.visualization.v1`. 계산 result JSON이나 canonical OCEL의 대체 저장 형식은 아님 |
| SVG | 선택한 그리기 panel의 그림 | 화면의 `Save SVG` 사용. metadata에 해당 panel 데이터와 전체 출처 목록·scope를 보존. 표 panel에는 SVG 그림이 없음. PNG/PDF 생성 API는 현재 없음 |

```python
from pix.viewer import read_visualization, render_html, export_html_report

restored = read_visualization("case-analysis.visualization.json")
html_text = render_html(restored)
publication = export_html_report(restored, "restored-analysis.html")
```

`export_html`은 저장 경로를 반환하고, `export_html_report`는 파일 identity와 publication 결과를 반환한다. 저장 API는 기본적으로 기존 파일 덮어쓰기를 거부한다. `overwrite=True`는 동일 파일을 갱신할 때 명시한다.

시각화 JSON은 큰 정수를 손실 없이 보존한다. HTML 내보내기는 절댓값 `2**53 - 1`을 초과하는 정수를 거부한다. 브라우저의 일반 숫자 타입으로 정수 identity가 바뀌는 것을 피하기 위한 처리다. 해당 자료는 native JSON으로 저장해 보존할 수 있다. 화면에 줄인 label이나 반올림한 축 눈금이 있어도 저장된 원값이 바뀌지는 않는다.

## 기존 viewer와의 관계

기존 `build_graph(result)`와 `build_model_graph(model)` 호출은 각각 기존 `GraphDocument`와 `ModelGraphDocument`를 만든다. **이 문서들 역시 기본 배치는 Graphviz다.** 기존 type filter·계수 선택·근거 조회는 유지한다. 신규 문서와 기존 문서의 계약은 그대로 구별하며 기본 배치만 함께 변경한다.

`render_html`, `export_html`, `export_html_report`에는 같은 `layout_engine` 인자를 사용한다.

| 값 | 신규 `VisualizationDocument` | 기존 `GraphDocument` / `ModelGraphDocument` |
|---|---|---|
| `"graphviz"` | 기본값 | 기본값 |
| `"native"` | 명시적으로 선택하는 실험용 배치 | 거부 |
| `"elk"` | 거부 | 명시적으로 선택하는 기존 배치 |

예를 들어 `export_html(view, "analysis.html", layout_engine="graphviz")`는 기본 동작을 명시한다. 배치 실패 시 다른 엔진으로 자동 전환하지 않는다. 표·행렬·차트·타임라인·chevron의 도메인 축은 graph용 `layout_engine` 설정으로 바뀌지 않는다.

새 표현이 필요하면 공개 `GraphPanel`, `MatrixPanel`, `ChartPanel`, `TimelinePanel`, `ChevronPanel`, `TablePanel`을 명시적으로 구성할 수 있다. 그 경우 숫자·단위·관계 의미와 출처는 공급자가 정의해야 한다. 범용 panel에 수치를 넣었다는 이유만으로 PIX가 그 수치를 계산·검증했다고 표시할 수는 없다.

JavaScript 통합 지점인 `PIXVisualization.mount(container, document, {layout})`은 대체 geometry 함수를 받는다. renderer가 node/edge ID와 유한한 좌표를 검사하므로 배치 엔진을 바꾸면서 관계를 바꾸어서는 안 된다. 신규 문서에 ELK/Cytoscape/Sigma 어댑터가 모두 구현되어 있다는 뜻은 아니다.

이 가이드의 지원 판단은 위 작성 시점의 계약·테스트에 유효하다. 모델 ID, shared event, 수치 단위, unknown 상태가 화면에서 달라지는 반례가 나오면 해당 adapter를 재검토해야 한다. 실제 데이터에서 읽기 쉬움·성능이 충분한지는 별도 판단이며, 비교 실측이 없는 우위나 최대 처리량은 알 수 없음이다.
