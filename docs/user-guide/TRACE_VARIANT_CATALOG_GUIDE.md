# Trace 빈도 목록과 여러 sequence 함께 보기

`catalog_trace_variants`는 그룹별 활동열을 `value_counts()`처럼 빈도순으로
나열한다. 정상/비정상 또는 그룹 A/B/C의 여러 variant를 한 화면에서 선택한다.

## 바로 실행

```bash
python -m pip install -e .
python examples/trace_variant_catalog_demo.py
```

`.artifacts/trace-variant-catalog/catalog.html`을 브라우저에서 연다.
정상 그룹의 합성 예제는 5 variants, 100 cases다.

| 조작 | 선택한 variants | 포함된 cases |
| --- | --- | --- |
| Top 20% variants | 1/5 (20%) | 60/100 (60%) |
| Top 80% variants | 4/5 (80%) | 95/100 (95%) |
| Top 100% variants | 5/5 (100%) | 100/100 (100%) |

1. 빈도·case 비율·누적 case 비율을 확인한다.
2. 상위 20/80/100% 버튼 또는 그룹별 0~100 정수 입력으로 선택한다.
3. 체크박스로 드문 경로를 추가/제외하고 아래 여러 sequence 행을 함께 본다.
4. 활동 노드를 눌러 실제 예시 case/event ID를 확인한다.
5. Save selection으로 선택 JSON, Save SVG로 현재 그림을 저장한다.

검색은 목록 행을 찾고 그룹 표시 체크는 그림의 그룹을 숨긴다.
어느 쪽도 원본 빈도·분모·선택 집합을 바꾸지 않는다. 표는 페이지로 나뉜다.

## 20%의 뜻

고유 variant 수 V에 대해 상위 p%는 `ceil(V*p/100)`개다.
7개에서 20%는 2개이므로 실제 variant 비중은 약 28.57%다.
요청 비중, 실제 variant 개수/비중, 포함 case 개수/비중을 구별한다.
빈도 동률은 기존 활동 tuple 사전순이며 경계 동률 전체를 추가하지 않는다.
누적 case 비율은 표의 참고값이고 선택 임계값이 아니다.

## 자신의 데이터

```python
from pix.case_centric import catalog_trace_variants
from pix.case_centric.trace_catalog import TraceCatalogSpec
from pix.contracts.result import ComputeStatus
from pix.viewer import build_visualization, export_html

# log는 CaseLog, quality_group은 case 속성 이름이다.
result = catalog_trace_variants(
    log, group_attribute="quality_group",
    spec=TraceCatalogSpec(top_variant_percent=20),
)
if result.status is ComputeStatus.COMPUTED:
    export_html(build_visualization(result), "catalog.html", layout_engine="native")
else:
    print(result.status, result.issues)
```

`pix.case_centric.trace_comparison.TraceGroup`의 tuple을 `groups=`로
전달해 명시적 case 목록도 사용할 수 있다. 겹치는 그룹, 모르는 ID,
이 API에 불필요한 대표 case 지정은 거부한다. 그룹 인자가 없으면 전체를 한 그룹으로 본다.
미라벨 case는 unassigned, 빈 그룹 비율은 N/A, 빈 sequence는 유효한 variant다.
활동 분류 실패를 빈 sequence로 바꾸지 않는다.

순서는 CaseTraceSpec을 따른다. 기본은 CaseLog 기록 순서다. OCEL은 명시적
case 투영 후 사용하고 receipt를 보관한다. 순서와 반복이 같은 활동 tuple만
묶는다. 각 행의 event IDs는 case ID 사전순으로 고른 실제 예시 case 하나의 IDs다.

## 저장과 한도

계산 결과는 `pix.results.write_result/read_result`, 화면 문서는
`pix.viewer.write_visualization/read_visualization`으로 왕복한다.
브라우저 선택 JSON은 별도 `pix.trace_catalog_selection.v1` 형식이다.
catalog_id는 source digest·computation identity·payload에 결합된다.
다른 데이터/profile의 선택은 거부한다. Load variant selection으로 선택·검색·그룹 표시를 복원한다.
SVG metadata에도 실제 선택을 보존한다. 원 계산 JSON은 화면 선택 때문에 바뀌지 않는다.

기본 계산 한도는 10,000 variants와 1,000,000 events다. 초과하면 잘린 목록을
완전한 것처럼 반환하지 않고 unavailable을 반환한다. 화면의 그룹/sequence cell
한도는 별도이며 선택과 원 catalog를 자르지 않는다. 대규모 성능은 아직 측정하지 않았다.

행은 원 sequence다. 열 위치가 같아도 정렬·시간·인과 대응을 뜻하지 않는다.
기준 대표와 정렬된 차이는 기존 [대표 비교](TRACE_GROUP_COMPARISON_GUIDE.md)를 사용한다.
공통 노드 기반 대표 선정, 집계 DFG, 새 multi-alignment는 후속 검토한다.
