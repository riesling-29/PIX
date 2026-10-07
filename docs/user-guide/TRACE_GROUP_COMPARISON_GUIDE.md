# 라벨별 대표 Trace 비교

정상/비정상, 장비 A/B/C 등 **이미 부여한 그룹 라벨**로 case를 나누고,
그룹의 실제 대표 sequence를 같은 화면에서 비교한다. 이 기능이 정상 여부를
자동 판정하거나 그룹 차이의 원인을 증명하지는 않는다.

## 먼저 화면 열기

```powershell
python examples/trace_group_comparison_demo.py --output .artifacts/trace-group-comparison
```

생성된 `comparison.html`을 브라우저에서 연다. 예제는 합성 데이터이며 정상,
재작업, 검사 생략의 세 그룹과 라벨 없는 case 하나를 포함한다. 웹 서버나
브라우저 측 Python은 필요하지 않다. 같은 이름으로 다시 만들 때만
`--overwrite`를 명시한다. 원 계산 JSON과 시각화 JSON도 같은 폴더에 생성한다.

- **Reference group**: 기준 그룹을 선택한다. 정상이라는 이름에 특별한 계산 의미는 없다.
- **Representative for …**: 그룹별 대표 후보를 선택한다. 다른 탭을 열지 않는다.
- 그룹 체크박스: 같은 캔버스에서 보고 싶은 그룹을 선택한다. 기준 그룹은 항상 보인다.
- **Differences only**: 보이는 그룹에서 차이가 있는 정렬 열만 남긴다. 원 결과는 유지한다.
- 활동·그룹 이름 클릭: 원 활동명, case/event ID, 편집 비용, variant 구성 case 등을 확인한다.
- **Save SVG**: 현재 기준·대표·표시 그룹·차이 필터 상태를 설명과 함께 내보낸다.

기본 대표는 그룹에서 가장 많이 등장한 **정확한 활동 sequence**의 실제 case다.
동률이면 활동 tuple의 사전순, 같은 sequence 안에서는 case ID 사전순으로 정한다.
화면의 `2/3 (66.67%)`는 해당 sequence의 case 수 / 그 그룹 전체 case 수다.
전체 자료나 선택 후보만을 분모로 쓰지 않는다. 그룹 카드에는 전체 variant 수와
표시 후보가 설명하는 case 수도 별도로 나온다. 대표 한 개가 그룹 전체를 설명한다는
뜻은 아니다. 화면의 소수점은 표시 반올림이며 원 membership은 JSON에 보존한다.

## 이미 라벨이 case 속성에 있는 경우

```python
from pix.case_centric import compare_trace_groups
from pix.case_centric.trace_comparison import TraceComparisonSpec
from pix.viewer import build_visualization, export_html

result = compare_trace_groups(
    log,  # PIX CaseLog
    group_attribute="quality_group",
    spec=TraceComparisonSpec(reference_group="정상", candidates_per_group=3),
)
view = build_visualization(result, title="정상 / 비정상 대표 흐름")
export_html(view, "group-comparison.html")
```

그룹 속성은 string, boolean, int를 지원한다. boolean 표시 이름은 `true`/`false`,
int는 10진 문자열이다. 타입은 다른데 표시 이름이 같으면 명시적 그룹을 요구한다.
누락 또는 null 라벨은 **unassigned**로 보존한다. 빈 문자열·복합 속성·float/date를
암묵적으로 범주화하지 않는다. case 속성의 기존 global-default 규칙은 적용한다.

## 직접 그룹을 지정하거나 대표 case를 고정하는 경우

```python
from pix.case_centric.trace_comparison import TraceGroup

result = compare_trace_groups(
    log,
    (
        TraceGroup("정상", ("case-01", "case-02", "case-03")),
        TraceGroup("비정상", ("case-04", "case-05"),
                   representative_case_id="case-05"),
        TraceGroup("그룹 C", ("case-06", "case-07")),
    ),
)
```

그룹은 서로 겹치지 않는 실제 case ID로 정의한다. 누락된 case는 unassigned에
남고, 중복 membership·없는 ID·그룹 밖의 수동 대표는 거부한다. 수동 대표가
최빈 후보 밖에 있으면 마지막 후보 자리를 대체하여 포함한다. 지정 case와 같은
sequence의 실제 빈도는 유지하며, 선택 방식은 `manual`로 표시한다.

라벨을 붙이는 것은 이 그룹 정의 또는 원 case 속성으로 수행한다. 현재 HTML은
계산한 그룹과 후보의 선택 화면이며 원 로그의 라벨을 수정·저장하는 편집기는 아니다.

## 정렬의 정확한 의미

각 선택 대표를 기준 대표에 **독립적으로 weighted edit alignment**한다.
기본 삽입·삭제·치환 비용은 1, 일치는 0이다. 같은 활동의 반복 occurrence와
원 event ID를 유지한다. `TraceComparisonSpec(alignment=SequenceAlignmentSpec(...))`으로
비용과 pair별 DP cell 한도를 바꿀 수 있다.

| 표시 | 의미 |
| --- | --- |
| Match / `=` | 기준과 같은 활동 |
| Additional activity / `+` | 대상에 있고 해당 정렬의 기준에는 없는 활동 |
| Missing activity / `−`, `∅` | 기준 활동에 대응하는 대상 활동이 없음 |
| Substitution / `↔` | 기준과 다른 활동으로 정렬됨 |
| Reference / `●` | 선택한 기준의 활동 |

기준 앞·사이·뒤의 삽입 위치를 공유해 여러 행을 한 화면에 배치한다. 삽입 활동은
각 행의 순서대로 배치되며, **서로 다른 대상 그룹의 삽입끼리 같은 열에 있다는
사실만으로 서로 대응·동일하다고 해석하지 않는다.** 여러 sequence를 동시에
최적화한 multiple alignment가 아니다. 기준 변경 시 해석과 비대칭 비용이 달라질 수
있다. 칸 폭·정렬 위치는 시간이 아니며, 활동의 재정렬은 편집 증거이지 원인 판정이 아니다.

## 지원 범위와 한도

- CaseLog의 기록된 순서를 사용한다. timestamp로 몰래 재정렬하지 않는다.
- OCEL은 객체형·순서 정책을 명시해 `project_object_cases`로 만든 CaseLog를 전달한다.
  `build_visualization(result, projection=projection)`으로 투영 근거를 함께 보존할 수 있다.
  이 비교는 해당 case 투영에 대한 것이며 OC 공유 사건·객체 간 partial order 전체의
  동등성 비교가 아니다.
- 그룹마다 기본 3개 후보, 전체 기본 64개 후보, pair당 기본 1,000,000 DP cells,
  모든 방향별 pair 합산 기본 4,000,000 cells다. 후보 수 한도 초과는 unavailable,
  pair·합산 한도 초과는 해당 pair를 미계산으로 남기고 partial로 표시한다.
- 모든 다른 그룹의 후보 쌍을 양방향으로 사전 계산한다. 브라우저의 기준·대표 변경은
  이 증거를 선택할 뿐 새 mining을 수행하지 않는다. 기본 한도는 검증된 처리량 보장이 아니다.
- case가 없는 그룹과 활동이 없는 빈 trace를 구분한다. 전자는 대표 없음, 후자는
  실제 빈 sequence이며 비교 가능하다. 불완전 trace 입력은 거부/미지원 상태를 보존한다.
- 브라우저 기본 12,000 표시 cells를 초과하면 명시적으로 안내한다. 일부 그룹을 조용히
  버리지 않는다. 원 JSON과 membership은 그대로 보존된다.
- 대표 후보 확장, 그룹 재정의, 실제 시간 비교는 Python에서 다시 계산해 HTML을 생성한다.

판단의 유효 범위는 해당 source digest, 그룹 membership, classifier와 정렬 비용이다.
이들 중 하나가 바뀌면 비교를 다시 계산해야 한다. 처리량·업무 원인·그룹의 실제
정상 여부는 이 화면만으로 알 수 없다.
