# PIX 객체 trace 규칙 평가 v1

기록일: 2026-09-10. 구현 식별자는 `pix.evaluate_constraints`, 연산자 버전은
`1.0.0`이다. 이 문서는 PIX가 명시한 규칙 의미와 검증 범위를 기술한다.
OCPA constraint monitoring 또는 Declare 도구 전체와 의미가 같다는 주장은 하지 않는다.

## 입력에서 판단까지

1. 유효한 canonical OCEL에서 대상 객체형, E2O qualifier, 동일 시각 순서 정책을
   명시하여 객체별 trace를 복원한다. 고립 객체도 빈 trace 하나로 남는다.
2. 고유 규칙 ID를 가진 규칙 목록과 관측 종료 가정을 지정한다. 규칙은 정확히 일치하는
   activity label을 사용한다. 이름이 비슷한 활동이나 객체 관계를 자동 결합하지 않는다.
3. 각 규칙·객체에서 검사 의무를 만들고 충족·위반·판단 대기 상태와 event ID를 기록한다.
4. 의무 수와 객체 수를 별도 집계한다. 전체 규칙을 섞은 fitness나 종합 점수는 만들지 않는다.

입력은 `reconstruct_traces`가 반환한 `ComputationResult[TraceSet]`이다.
부분적으로 복원한 모집단은 검사하지 않는다. 원래 입력 오류는 `invalid_input`으로
보존하며, 다른 미완료 입력은 원래 진단을 포함한 `unavailable`로 반환한다.
수동으로 조작한 trace의 중복 객체/event, 역순 시각, 비 UTC 시각, 다른 객체를 가리키는
E2O 등도 거부한다. 원래 trace 계산 ID와 canonical source digest가 결과에 연결된다.

## 제공하는 규칙

아래의 선후관계는 선택한 trace 안의 **엄격한 occurrence 순서**다. 같은 이름을 양쪽에
사용해도 자기 자신을 증거로 삼지 않는다. A→A에서 A가 한 번이면 후행/선행 의무는
충족되지 않는다. 한 B가 여러 A의 response를 충족할 수 있다.

| 규칙 | 조건 | 의무 모집단 | 충족 증거 선택 |
|---|---|---|---|
| Count | A 횟수가 닫힌 구간 `[min_count,max_count]`에 속함. 상한 `None`은 무제한 | 선택한 객체당 1개 | 관측한 모든 A event ID와 횟수 |
| Response | 관측한 각 A 뒤에 B가 존재 | 관측한 A occurrence | 첫 후행 B |
| Precedence | 관측한 각 B 앞에 A가 존재 | 관측한 B occurrence | 가장 가까운 선행 A |
| Not coexistence | 한 객체 trace에 A와 B가 함께 존재하지 않음 | 선택한 객체당 1개 | 관측한 A/B event ID |
| Timed response | 관측한 각 A 뒤의 B가 `[min_microseconds,max_microseconds]`를 만족 | 관측한 A occurrence | 명시한 `any` 또는 `first` 정책 |

존재 규칙은 Count `(1,None)`, 부재는 `(0,0)`, 정확히 n회는 `(n,n)`으로 지정한다.
Not coexistence의 A와 B가 같은 label이면 그 label의 존재를 금지한다.
Count와 Not coexistence는 빈 객체에도 검사 의무가 한 개이며 vacuous로 처리하지 않는다.

Timed response의 `any`는 시간 범위 안에 있는 후행 B 중 첫 것을 증거로 선택한다.
`first`는 첫 후행 B 자체가 시간 범위 안에 있어야 한다. 예를 들어 A가 0μs,
B가 5μs와 10μs에 있고 범위가 `[10,20]`이면 `any`는 충족, `first`는 위반이다.
두 끝점은 포함한다. 정수 μs 차이를 사용하며 부동소수점 초로 변환하지 않는다.

## 관측 종료 가정

`observation_policy`에는 기본값이 없다. 호출자가 다음 중 하나를 선택한다.

| 상태 | 의미 |
|---|---|
| `closed` | 선택한 모든 객체 trace를 완결된 관측으로 선언한다. 필요한 후행 event가 없으면 위반이다. |
| `open` | 선택한 모든 객체 trace를 시간 역행 없이 뒤에만 event가 추가되는 prefix로 선언한다. 아직 충족/위반을 확정할 수 없는 의무는 pending이다. |

열린 관측에서 Count의 하한 미달은 pending이고 상한 초과는 확정 위반이다.
하한을 채웠고 상한이 무제한이면 충족이다. 유한 상한을 넘지 않았다는 사실만으로는
이후 초과 가능성을 배제할 수 없으므로 pending이다. Not coexistence도 두 label이
이미 함께 있으면 위반, 그렇지 않으면 pending이다.

Response의 관측한 후행 B는 해당 의무를 충족하고, 없는 B는 pending이다.
Precedence의 과거는 뒤에만 추가하는 가정하에서 바뀌지 않으므로 충족/위반을 확정한다.
Timed response의 `first`가 범위 밖이면 이후 B가 있어도 그 의무는 위반이다.
`any`에서 적격 B가 없더라도 해당 객체의 마지막 관측 시각이 A의 상한 deadline을
**엄격히 지났으면** 이후 추가로 고칠 수 없어 위반이다. 마지막 시각이 deadline과
같으면 같은 시각의 B가 추가될 수 있으므로 pending이다. 이 판정의 증거에는
A와 deadline을 지난 마지막 event ID가 들어간다. 전역 watermark나 현재 벽시계 시각은
사용하지 않는다.

동일 시각은 기존 `TraceSpec.tie_policy`를 따른다. `reject`는 복원을 거부한다.
`event_id`는 event ID의 사전순을 적용하고 결과에 `event_id_order_assumption`을 남긴다.
선택한 순서에서 뒤에 있는 다른 event는 시간 차 0μs의 response일 수 있다.
이 순서는 인과관계를 입증하지 않는다.

열린 trace에서 아직 A가 없는 Response는 관측 activation이 0개이다. 해당 객체의
현재 판정은 vacuous fulfilled이며 비율은 없음이다. 이는 모든 미래 continuation이
규칙을 지킨다는 뜻이 아니다. 미래의 미관측 activation은 모집단에 넣지 않는다.

## 결과를 읽는 방법

`ConstraintEvaluation`은 객체형, trace 계산 ID, 관측 정책, 요청 순서의 규칙 결과를
담는다. `RuleEvaluation`은 규칙 ID·종류·모집단과 다음 값을 담는다.

- `activation_count = fulfilled_count + violated_count + pending_count`이다.
  `population=object_traces`인 규칙에서 activation은 객체당 검사 의무라는 뜻이다.
- `fulfillment_ratio=(fulfilled_count,activation_count)`는 약분하지 않은 정확한
  분자·분모다. pending도 분모에 포함하며, 분모가 0이면 `None`이다.
  이 값은 관측한 의무의 현재 충족 비율이며 완결된 적합성 점수가 아니다.
- 객체 수와 충족·위반·대기 객체 수는 별도로 제공한다. 객체 판정 우선순위는
  위반, pending, 충족이다. 그러므로 위반 객체에도 pending 의무가 남을 수 있다.
- `vacuous_object_count`는 관계 규칙에서 관측 activation이 0개인 객체 수다.
- 객체별 `TraceRuleEvaluation` 안의 witness가 activation event ID, 증거 event ID,
  관측 횟수 또는 선택한 event 쌍의 정확한 시간 차, 판정 이유를 제공한다.

계산 상태 `computed`는 검사 계산을 마쳤다는 뜻이며 규칙이 모두 충족됐다는 뜻이
아니다. pending 의무가 하나라도 있으면 `partial`이다. 선택한 객체가 0개이면
모든 모집단 수는 0, 비율은 `None`, 결과에는 `empty_population` 진단이 들어간다.
이를 객체 하나의 빈 trace와 구분한다. 서로 다른 규칙 결과를 합한 종합 비율은 없다.

## 확인한 검증 범위와 제한

주 테스트 파일은 `tests/compute/test_constraints.py`와
`tests/compute/test_constraint_truth_oracle.py`다. 후자는 구현 내부 함수를 부르지 않고
A/B/C 길이 0–5의 모든 364개 word에 독립적인 양화 논리식을 적용한다. 123개 규칙
조건을 비교하므로 규칙·trace 조합은 44,772개다. 자기 label 규칙, 분모 0,
충족·위반 수뿐 아니라 activation별 witness 상태도 비교한다.
별도 표적 테스트는 열린 관측, 같은 시각, 불규칙 시간 간격, 양 끝점, 첫/아무 response,
증거 선택, 잘못된 입력, 원래 오류의 보존, 계산 ID를 검증한다.

이 규칙들은 객체별 trace-local 검사다. 여러 객체 사이의 결합 의무, O2O 기반
업무 규칙, 속성 조건식, 비율 threshold, mixed completion policy, late-arrival 보정,
alternate/chain/negative response, 종합 Declare 모델 채굴은 이 버전에 없다.
현재 evaluator는 규칙·activation별로 후보를 탐색하는 직접 구현이다. 대용량 처리량과
기존 라이브러리 대비 성능은 **알 수 없음**이다.

판단 유효 범위는 기록된 버전과 시험 데이터에 한정한다. 반례, trace 순서 변경,
닫힘 가정의 오류, 늦게 도착한 event의 과거 삽입, 규칙 의미 변경이 확인되면 영향을
받는 판정을 철회하고 전체 해당 trace를 다시 계산해야 한다. 유한 oracle 통과는
모든 로그에 대한 증명이 아니다.
