# PIX 시각화 문서 계약 — 2026-09-15

이 문서는 계산 결과를 화면으로 옮기는 데이터 구조를 정의한다. 계산 알고리즘이나 그 결과의 타당성을 판정하는 규약은 아니다. 기존 `GraphDocument`와 `ModelGraphDocument`의 필드·검증은 변경하지 않고, `pix.viewer.visual_contracts`에 별도 계약을 추가한다.

**2026-09-16 확장:** 전용 `ChevronPanel`과 객체 instance·shared-event 계약을 추가한다. Graphviz를 모든 graph의 기본 배치로 사용하는 결정은 [변경 요구사항](../requirements/2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md)에 기록한다. 배치 엔진 변경은 원본 계산·시각화 문서의 의미를 변경하지 않는다.

## 계산과 화면의 경계

`VisualizationDocument`는 제목, 패널, 출처, 이슈, 표시 상태를 갖는다. 하나의 계산을 그래프와 표로 동시에 설명하거나, 동일한 문서에서 모델과 실제 실행을 함께 제시할 수 있다. 각 패널은 표시할 데이터를 받으며, 이벤트 순서·빈도·fitness 등을 새로 추정하지 않는다. 화면 픽셀 좌표와 HTML·JavaScript는 저장 계약에 들어가지 않는다. Chevron의 선행관계 슬롯은 픽셀 좌표가 아닌 표시 의미이므로 문서에 보존한다. 같은 JSON을 다른 배치 엔진이나 UI에서도 사용할 수 있다.

모든 계약은 `frozen=True, slots=True` 데이터클래스이고, 컬렉션은 튜플이다. 생성할 때 검증하며, JSON으로 내보낼 때에도 다시 검증한다. `object.__setattr__`로 강제로 수정한 인스턴스가 잘못된 데이터를 그대로 내보내는 경우도 거부한다. 다만 Python 객체를 악의적으로 조작하는 코드를 격리하는 보안 장치는 아니다.

공개 생성자는 다음과 같다. 기본값은 구현 파일에서 확인할 수 있으며, 이름은 JSON 키와 동일하다.

| 계약 | 핵심 필드 | 의미 |
| --- | --- | --- |
| `VisualizationDocument` | `title, panels, provenance, issues, status` | 전체 표시 문서. `schema`는 `pix.visualization.v1`로 고정된다. |
| `VisualProvenance` | `calculation_id, source_digest, model_digest, operator_id, status, details, panel_ids, input_path` | 계산·원본·모델의 선언된 출처와 각 출처에 속하는 패널·입력 위치. |
| `GraphPanel` | `id, title, nodes, edges, layout, description` | 방향 그래프 또는 무방향 그래프. |
| `MatrixPanel` | `id, title, rows, columns, cells, legend, unit, description` | footprint, 유사도 등 행렬. 값의 의미를 명시해야 한다. |
| `ChartPanel` | `id, title, chart_type, series, x_type, x_label, y_label, x_unit, y_unit, description` | 막대·선·산점도. |
| `TimelinePanel` | `id, title, lanes, items, axis_type, unit, description` | 객체·케이스별 실제 시각 또는 상대 순서. |
| `ChevronPanel` | `id, title, lanes, events, variant_id, frequency, population, description` | 객체 instance별 OC execution의 선행관계 슬롯과 공유 사건. |
| `TablePanel` | `id, title, columns, rows, description` | 타입을 유지한 원시 근거와 상세 값. |

패널의 `kind`는 생성자가 설정한다. 각각 `graph`, `matrix`, `chart`, `timeline`, `chevron`, `table`이며 임의로 다른 종류를 선언할 수 없다. 문서의 `status`는 `ok`, `partial`, `unsupported`, `error` 중 하나다. 이는 시각화 문서의 표시 상태다. 원본 계산의 상태는 `VisualProvenance.status`에 원래 문자열 그대로 보존하며, `ok`가 계산의 정확성을 인증하지 않는다.

`VisualProvenance.panel_ids`는 해당 출처에 속하는 패널 ID의 튜플이다. 중복과 빈 ID는 허용하지 않고, 명시한 모든 ID는 문서에 실제로 존재해야 한다. `input_path`는 합성 문서 안에서 입력이 온 위치를 나타내는 0 이상의 정수 튜플이며, bool은 허용하지 않는다. 예를 들어 `(1, 0)`은 두 번째 입력 안의 첫 번째 입력이다. 합성 시 패널 ID에 prefix를 붙이면 이 참조도 함께 변경하고, 중첩 입력 경로도 유지해야 한다. 이 두 필드는 기존 `details` 뒤에 추가되어 기존 위치 인자 호출을 유지한다.

두 필드가 모두 빈 튜플인 경우만 기존/custom 문서의 문서 전체·미지정 출처로 해석한다. `panel_ids=()`이면서 `input_path`가 비어 있지 않으면, 실패한 입력처럼 **연결된 패널이 없는 명시적 입력 범위**다. 이를 문서 전체 출처로 확대해서는 안 된다. `build_visualization`은 각 입력의 출처에 해당 패널 목록과 입력 경로를 붙이며, 문서 전체 출처를 다른 문서와 합칠 때에는 그 입력의 패널들로 범위를 한정한다. 기존 `VisualizationDocument` 하나만 전달하면 원 출처 연결을 그대로 유지하고, 요청한 경우 제목만 변경한다.

Inspector는 현재 패널 ID를 포함하는 출처와 문서 전체 출처만 표시한다. 패널 없는 실패 입력의 출처를 정상 패널의 근거로 보여주지 않는다. 문서 자체에 패널이 없으면 overview에서 이 출처를 `No associated panels`로 확인할 수 있다. JSON은 전체 문서의 출처와 범위를 보존하고, SVG metadata도 선택 패널 데이터와 함께 전체 출처 목록을 보존한다. 따라서 Inspector에서 출처가 보이지 않는 것과 산출물에서 그 출처가 삭제되는 것은 다르다.

## 그래프: 동일한 라벨과 동일한 객체를 구별한다

`VisualNode(id, label, kind="activity", group=None, metrics=(), details=())`와 `VisualEdge(id, source, target, label="", kind="flow", directed=True, metrics=(), details=())`를 사용한다.

같은 `Approve`라는 라벨을 가진 두 transition은 서로 다른 `id`를 유지한다. 노드 ID와 엣지 ID는 각각 패널 안에서 중복될 수 없다. 엣지 양 끝은 그 패널에 존재하는 노드여야 한다. 서로 다른 역할을 가진 같은 양 끝의 엣지는 서로 다른 ID로 표현할 수 있다. 자기 루프도 허용한다. ID를 라벨에서 재생성하거나, 라벨이 같다는 이유로 병합하지 않는다.

`kind`와 `group`은 의미를 보존하는 일반 문자열이며, 임의의 문자열을 코드나 HTML로 해석해서는 안 된다. `layout`은 `layered`, `tree`, `force`, `bipartite` 중 하나인 배치 요청이다. 예를 들어 `tree`라는 요청만으로 원본 그래프가 수학적인 트리라고 주장하지 않는다. renderer는 지원하지 않는 배치나 잘못된 입력 조건을 설명해야 하며, 계약 검증은 배치의 품질을 보증하지 않는다.

이 `layout`은 HTML exporter의 `layout_engine`과 별개다. 엔진 기본값은 `graphviz`이며 Graphviz가 위치·spline·label 좌표를 계산한다. `native`는 신규 문서에만 허용하는 명시적 실험 경로, `elk`는 기존 graph 문서에만 허용하는 명시적 경로다. 실패를 숨기며 다른 엔진을 선택하지 않는다. JSON 자체가 특정 엔진의 실행을 요구하지는 않는다.

측정값은 `VisualMetric(name, value, unit)`으로 나타낸다. 숫자 또는 `None`만 허용하며, bool은 숫자가 아니다. 값이 없다는 사실을 0으로 바꾸지 않는다. 단위는 필수 문자열이다. 같은 그래프에서 같은 이름의 metric을 다른 단위로 사용하는 것을 거부한다. 예를 들어 `frequency / events`와 `frequency / objects`를 한 metric처럼 합치려 하면 오류가 나므로, `event_frequency`, `object_frequency`처럼 구분해야 한다. 단위 문자열의 물리적 동등성을 해석하거나 변환하지는 않는다.

상세 정보는 `VisualField(name, value)`의 튜플이다. 값의 타입은 `str`, `int`, `float`, `bool`, `None`뿐이다. 같은 상세 필드 이름은 중복될 수 없다. 객체, 딕셔너리, 콜백, 임의 객체의 `repr`는 허용하지 않는다. 중첩 근거는 열을 정의한 별도 표로 펼치거나, **JSON 문자열이라는 사실을 명시한 필드**로 전달할 수 있다. 후자의 문자열 내용을 renderer가 실행하거나 임의 클래스로 복원해서는 안 된다.

## 행렬: 관측되지 않음과 검증되지 않음을 구별한다

`MatrixCell(row, column, value, kind="value", details=())`를 사용한다. 행과 열은 순서를 가진 고유 문자열 ID다. 같은 `(row, column)` 좌표가 두 번 나오거나, 선언되지 않은 행·열을 참조하면 거부한다.

셀이 있는 행렬에는 `legend: tuple[VisualField, ...]`가 반드시 있어야 한다. footprint의 `→`, `∥`, `#`와 수치 유사도는 서로 다른 의미이므로, 기호나 수치가 무엇을 뜻하는지 설명해야 한다. `None`이나 생략된 셀에 특정 의미를 자동으로 부여하지 않는다. 미계산, 관측 0, 불가능, 관계 없음은 생산자가 `kind`, legend, 값으로 구별할 책임이 있다. 희소 행렬을 완전한 행렬로 채우며 0을 추정하지 않는다.

## 차트와 타임라인: 시간 기준을 드러낸다

`ChartSeries(name, points=(), group=None)`와 `ChartPoint(x, y, details=())`를 사용한다. 시리즈 이름은 고유하며, 입력한 점의 순서를 보존한다. 같은 x에서 여러 관측값이 나오는 산점도 등을 위해 x 중복은 허용한다. 자동 평균이나 합계를 계산하지 않는다. y는 숫자 또는 `None`이다.

| x 타입 | 허용되는 값 | 예 |
| --- | --- | --- |
| `category` | 문자열 | `"Approve"` |
| `number` | 유한한 int 또는 float | 순서 1, 상대시간 2.5 |
| `time` | 아래 RFC3339 형식의 시간대 포함 문자열 | `"2026-09-15T09:00:00+09:00"` |

숫자 Unix timestamp를 차트에 사용할 때는 `x_type="number", x_unit="unix-seconds"`로 명시한다. `time`은 `YYYY-MM-DDTHH:MM:SS[.소수점 이하 1~6자리](Z|±HH:MM)`만 허용하고 실제 날짜·시각도 검증한다. Python이 읽을 수 있더라도 주차 기준 날짜, 구분자 없는 날짜, 공백 구분자, 시간대 없는 문자열, 초가 생략된 시각, 오프셋의 초·소수부는 거부한다. 브라우저가 공통으로 읽을 수 있는 형태로 제한하는 것이며, 입력을 조용히 정규화하지 않는다. 시간대와 6자리까지의 초 소수부도 원문 그대로 보존한다. 윤초 60은 현재 지원하지 않는다. `chart_type`은 `bar`, `line`, `scatter`다.

타임라인은 `TimelineLane(id, label, group=None)`과 `TimelineItem(id, lane, start, end, label="", group=None, status=None, details=())`를 사용한다. `axis_type="timestamp"`는 숫자 Unix epoch seconds이며, `unit="seconds"`를 요구한다. `axis_type="relative"`에서는 예를 들어 `unit="steps"`로 순서 축을 명시할 수 있다. 유한 숫자만 허용하고 종료가 시작보다 앞서면 거부한다. `end=None`은 열린 끝으로 그대로 보관하며, 현재 시각이나 임의의 종료 시각으로 바꾸지 않는다.

OCEL의 같은 이벤트가 여러 객체 lane에 나타날 수 있다. 이때 화면 항목 ID는 각각 다르게 지정하고, `VisualField("event_id", 원본ID)`로 공통 원본 이벤트를 보존한다. 화면 항목 두 개가 원본 이벤트 두 개라는 의미는 아니다. 이벤트 qualifier, 공동 참여 근거, 순서 tie 정책은 상세 필드나 표로 함께 제공해야 한다.

## Chevron: 객체 참여와 사건의 정체성을 분리한다

`ChevronLane(id, label, object_type, object_id, details=())`는 객체 하나의 행이다. `object_type`은 색 범주의 근거이고 `object_id`는 실제 객체다. 라벨이 같아도 객체 ID가 다르면 다른 행이다.

`ChevronEvent(id, label, start, end, lane_ids, details=())`는 **한 사건**이다. `lane_ids`는 그 사건에 참여한 행들의 목록이며, 행마다 사건 레코드를 복제하지 않는다. Renderer는 같은 레코드를 여러 행에 표시하면서 동일한 ID와 `[start, end]`를 보존한다. Qualifier가 여러 개라는 이유로 같은 객체 참여 행을 중복하지 않는다.

`start`와 `end`는 0 이상의 정수 슬롯이고 양끝을 포함한다. 따라서 `start == end`는 한 슬롯이며 열린 구간이나 0초 duration이 아니다. 실행 builder는 실제 선행관계 DAG에서 longest-path start를 구하고, 가장 빠른 후속 사건의 start 직전까지 end를 확장한다. 후속 사건이 없는 sink는 `end == start`다. 슬롯 폭을 seconds, waiting, service time 또는 빈도로 바꾸어 읽어서는 안 된다. 화면에 나타내기 위해 없던 선행관계를 추가하지 않는다.

`ChevronPanel(id, title, lanes=(), events=(), variant_id=None, frequency=None, population=None, description="")`은 위 행과 사건을 묶는다. Variant ID, 빈도와 모집단은 공급된 variant 계산에서 온 값이며, 선택한 대표 실행 자체의 사건 수와 구별한다. `None`은 미제공 값으로 보존한다. 공통 JSON codec이 다른 panel과 같이 이를 왕복하며, 알려지지 않은 kind나 누락된 참조는 거부한다.

`build_execution_chevrons`는 단일 실행의 표시 자료를 만들며, `build_variant_visualization`은 서로 일치하는 `COMPUTED` 상태의 정확한 `ExecutionSet`과 `VariantSet`만 검증해서 결합한다. 뒤 API는 source digest뿐 아니라 parent computation과 전체 execution partition·대표 실행·빈도 근거를 검사한다. Partial·실패, 미해결 tie·불완전 객체 경로·cycle은 거부하고, event ID로 명시적으로 해결한 tie는 `tie_broken` 근거로 공개한다. Canonical labeling을 다시 실행하지 않으므로 외부 payload의 그룹핑에 대해 동형성을 새로 증명하지 않는다. OCPA의 근사 variant 분류를 이 화면의 계약으로 도입하지 않는다. Raw helper는 객체 없는 사건·경계 객체에만 연결된 사건을 거부하며 variant helper는 해당 사건을 별도 표에 보존한다. 세부 경계는 [변경 요구사항](../requirements/2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md)을 따른다.

## 표와 숫자의 보존 범위

`TablePanel.columns`는 고유 문자열 튜플이며, 모든 행의 폭이 같아야 한다. 셀은 원시 scalar만 허용한다. `1`, `1.0`, `True`, `"1"`, `None`은 서로 다른 타입을 유지한다. 실수의 NaN과 무한대, 유효하지 않은 Unicode surrogate는 거부한다.

Python JSON 왕복에서는 임의 정밀도 정수와 `-0.0`도 보존한다. 그러나 이 사실이 JavaScript의 일반 `JSON.parse`가 큰 정수를 정확하게 표시하거나 계산한다는 의미는 아니다. HTML exporter는 JavaScript의 안전 정수 범위를 넘는 정수를 임베딩 전에 거부하는 정책을 사용한다. Python 전용 JSON 계약은 해당 정수를 계속 보존한다. 이 계약은 배치 좌표의 정밀도, 브라우저 숫자 연산, 원본 계산의 반올림 정확성을 검증하지 않는다.

## JSON 입출력

`pix.viewer.visual_serialization`이 다음 API를 제공한다.

```python
from pix.viewer.visual_contracts import TablePanel, VisualizationDocument
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization

document = VisualizationDocument(
    title="Alignment evidence",
    panels=(
        TablePanel(
            id="costs",
            title="Actual evaluated cases",
            columns=("case", "cost", "optimality_proven"),
            rows=(("case-1", 0, True), ("case-2", None, False)),
        ),
    ),
    issues=("case-2 has not completed.",),
    status="partial",
)
encoded = dumps_visualization(document)
assert loads_visualization(encoded) == document
```

`visual_to_dict`는 원본을 바꾸지 않는 별도 JSON 원시 값 사본을 반환한다. `visual_from_dict`는 완전한 JSON 형태의 딕셔너리를 검증한다. `dumps_visualization(document, indent=None)`은 키를 정렬한 결정적 JSON을 생성하고, 모든 패널·행·관측값의 순서는 보존한다. 인코딩에서 기본값을 생략하지 않는다. 디코더도 스키마의 모든 필드가 명시된 형태를 요구하므로, 알 수 없는 필드나 생략된 필드를 조용히 무시하지 않는다.

`loads_visualization(text, max_bytes=64*1024*1024)`는 UTF-8 문자열 또는 바이트를 받는다. 중복 JSON 키, 잘못된 UTF-8, NaN/Infinity, 알 수 없는 schema·kind, 크기 초과, 과도한 중첩을 거부한다. 최대 크기는 입력 바이트에 대한 한도이며, 프로세스 전체 메모리 사용 상한은 아니다. 큰 문서를 의도적으로 읽을 때 한도를 명시적으로 늘릴 수 있다. 데이터의 일부를 잘라 성공으로 처리하지 않는다.

JSON 디코딩은 고정된 계약 클래스 목록만 사용한다. 입력의 클래스명, 모듈 경로, 코드 문자열을 실행하거나 동적으로 import하지 않는다. HTML처럼 보이는 라벨도 원문 데이터로 보존한다. 실제 HTML 내보내기의 escaping, CSP와 DOM 처리 검증은 exporter/UI의 별도 책임이다.

## 현재 검증과 판단 범위

2026-09-15의 독립 계약 테스트 `tests/viewer/test_visual_contracts.py`는 158개가 통과했다. 다섯 패널의 실제 JSON 왕복, scalar 타입 구분, 동일 라벨의 별도 ID, provenance 상태와 패널 소유권·중첩 입력 위치 보존, 누락값·열린 종료, 단위 충돌, 잘못된 차원·참조·시간대, RFC3339 시각 형식과 소수부 보존, 입력 오염과 악성 JSON을 검사했다. Ruff 검사도 통과했다. 이 수치는 해당 테스트 파일의 결과이며, 전체 PIX 회귀 결과나 실제 브라우저 시각 품질 점수가 아니다.

위 숫자는 2026-09-16 Graphviz 기본값·ChevronPanel 확장 전의 역사 기록이다. 새 필드·슬롯·shared-event 표시·출처 결합·브라우저와 wheel 검사는 변경 후 별도 실행 증거로 판정한다.

계약의 유효 범위는 위 schema와 현재 생성자다. schema, 패널 의미, 숫자·시간 정책을 바꾸면 이 문서와 왕복·오류 테스트를 함께 갱신해야 한다. 타입 손실, 동일 ID의 오병합, 미계산 값을 0으로 대체하는 사례, 또는 미지원 필드를 묵살하는 입력이 발견되면 해당 보존 주장을 철회하고 회귀 사례를 추가한다. PM4Py/OCPA의 모든 visualization을 동일하게 재현했다는 주장은 이 계약과 테스트만으로 할 수 없다.
