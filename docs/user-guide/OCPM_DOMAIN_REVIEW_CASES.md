# OCPM 도메인 검토 사례

2026-09-28 / OC-PATCH-02. 사례 2의 명시 모델 제약 위반은 사용자 판단을 반영했다. 그 밖의 사례까지 일괄 승인받았다고 기록하지 않는다. 모델의 명시 제약과 관측으로 발견한 cardinality를 혼동하지 않는다.

## 1. A→B를 무엇으로 세는가

| 사건 | 활동 | 객체 | 순서 |
| --- | --- | --- | --- |
| e1 | A | x, y | 1 |
| e2 | B | x, y | 2 |
| e3 | A | x | 3 |
| e4 | B | x | 4 |

x의 trace는 A→B→A→B이고 y는 A→B다. A→B에 대해 event pair는 `(e1,e2),(e3,e4)` 두 개, 객체는 x·y 두 개, 객체별 발생은 `(x,e1,e2),(y,e1,e2),(x,e3,e4)` 세 개다. 따라서 **2 / 2 / 3**이다. e1과 x의 qualifier를 하나 더 추가해도 값은 변하지 않는다. 비율을 계산하지 않았으므로 이 세 수의 '분모'는 없다.

기존 근거: `tests/compute/test_ocdfg.py::test_shared_and_repeated_pairs_distinguish_all_three_count_units`. viewer까지 보존되는지는 신규 domain-review 테스트에서 확인한다.

## 2. 객체별로는 적합하지만 공동 참여는 위반하는 경우

모델: 같은 객체형 T의 객체 x·y에 각각 초기 p token과 최종 q 요구가 있다. A transition의 p→A→q arc는 **non-variable arc**다. 따라서 이 모델의 binding은 해당 객체형 T에서 정확히 객체 하나를 선택한다. 로그에는 같은 T형의 x·y가 함께 참여하는 사건 e:A가 한 번 있다.

**최종 해석 정정 (2026-10-04 기록, 2026-09-28 대화 반영):** 이 조건은 non-variable arc에 연결된 객체형의 binding cardinality에 한정된다. 전체 이벤트의 객체 수를 항상 하나로 제한하거나, 독립 활동의 동시 실행을 금지하는 규칙이 아니다. variable arc에 동일 제약을 일반화하지 않는다. PIX의 variable arc `min_objects`/`max_objects`는 명시적 확장 profile 제약으로 구분한다. AND/XOR 활동 분기와도 별도 문제다.

Flattened replay는 x와 y를 각각 투영하여 A를 한 번씩 재생하므로 각 trace가 적합하다. 공동 replay는 두 객체가 동시에 참여하는 e를 한 객체씩의 별도 사건으로 임의 분할할 수 없다. 기존 profile은 해당 사건을 참여 제약 위반으로 기록한다. 두 계산을 평균·대체하지 않는다.

**사용자 결정 (2026-09-28):** 이 경우 원본은 현재 모델에 적합하지 않다. 공동 참여 제약 위반을 오류로 명확히 표시하며, flattened 적합성으로 원본 판정을 무효화하지 않는다. 이 동작을 허용하려면 별도의 프로세스 모델이 필요하다. 소비자 정책에 부적합 판정 자체를 다시 맡기는 것으로 해석하지 않는다.

계산 성공과 적합성은 구별한다. replay가 정상 완료되어 `computed`여도 `fitting=False`이면 모델 부적합이다. 이를 입력 파싱 오류나 탐색 한도 초과로 바꾸지 않는다. 별도 모델의 표현·제약은 명시적으로 설계해야 하며 이번 결정만으로 모델을 자동 생성·교체하지 않는다. DFG의 직접후행 집계가 객체 공동 참여 제약을 검사한 Petri-net replay를 대체하지 않는다. 표기마다 표현력·모델 의미를 따로 다룬다.

기존 독립 token 산술: `tests/object_centric/test_conformance.py`. 이는 token replay 사례이며 joint alignment의 최적 move 비용과 같은 지표가 아니다. 서로 다른 세 operator의 보장을 이 한 사례로 모두 증명하지 않는다.

## 3. 숫자가 같아도 같은 연산은 아니다

같은 모델에서 로그가 e1:A(x), e2:A(y)라면 두 사건은 각자 한 객체 제약을 만족한다. 공동 replay와 flattened replay 모두 적합하고 token fitness 1이 가능하다. operator identity와 분석 단위는 여전히 다르다. 따라서 '두 알고리즘의 숫자가 항상 달라야 한다'는 수락 기준은 사용하지 않는다.

## 4. 미확정과 다음 사례

projection에서 shared event로 생긴 case 간 연결과 자원 공유는 기존 boundary 테스트를 재사용한다. 선형화에 따른 n-gram 변화는 신규 사례로 추가 검토할 대상이다. 모든 sequence 순열을 동치로 취급하지 않는다. 현재 문서가 일반 sequential pattern mining이나 normative OCPN soundness를 승인하지 않는다.

예제의 모델 제약·모집단·비용 정책이 달라지면 기대값과 해석을 다시 검토한다. 조회한 profile과 독립 token 산술이 불일치하면 구현 또는 이 문서의 기대값을 근거와 함께 수정한다.

## 5. 원본 투영 receipt를 Case DFG에 연결하기

```python
from pix import case_centric as cc
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec, project_object_cases,
)
from pix.viewer import build_visualization

projection = project_object_cases(ocel, ObjectCaseProjectionSpec("Order"))
result = cc.discover_dfg(projection.case_log)
document = build_visualization(result, projection=projection)
```

`projection=`은 선택 인자다. 단일 CaseLog 또는 그 파생 digest를 가진 계산 결과만 받을 수 있다. receipt의 source/spec로 투영을 다시 계산해 대응을 검사하고 입력의 case digest를 대조한다. 잘못된 receipt는 `ValueError`이며 자동으로 버리거나 다른 원본을 추측하지 않는다. 이 검사는 전달받은 snapshot 내부의 일관성을 확인하는 것이지 외부 수집의 진실성·인증을 보증하지 않는다. 추가 비용은 선택 경로의 투영 재계산이며 성능은 아직 측정하지 않았다.

여러 분석을 함께 표시하려면 각 단일 입력을 먼저 `build_visualization(..., projection=...)`로 만들고 그 문서들을 `build_visualization(doc1, doc2)`로 합친다. receipt는 원래 panel에만 연결된다. 기존 receipt 없는 호출과 저장 문서는 계속 지원한다. receipt가 없으면 그 provenance를 복원했다고 주장하지 않는다.

화면과 SVG의 interpretation 영역은 해당 panel의 operator/status/diagnostics와 투영 설명을 읽는다. shared-event case sets는 원본 이벤트별 참여 case 집합을 중복 제거한 것으로, source event 수나 transitive component 수가 아니다. 모델만 읽은 입력에 관측적 discovery 보장을 임의 추가하지 않는다.

실행 가능한 합성 예제:

```powershell
python examples/ocpm_projection_review.py --output <새 출력 디렉토리>
```

`projection-review.html`과 JSON을 생성한다. 첫 OCDFG와 뒤의 투영 Case DFG는 동일 원본에서 나왔지만 집계 단위가 다르다. 예제는 실제 업무 데이터가 아니다. 기존 출력은 자동 덮어쓰지 않는다.
