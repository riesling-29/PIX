# PIX 객체 문맥별 행동 적합성·정밀도 v1

이 문서는 `pix.object_context.binding_prefix.v1`의 의미와 검증 범위를 고정한다.
구현 연산자는 `pix.measure_object_context`, Python 진입점은
`measure_object_context(log_or_context, net, ObjectContextSpec(...))`다.
OCPA의 수치를 재현하는 호환 프로필이나 alignment fitness라는 뜻은 아니다.

## 무엇을 비교하는가

선택한 객체들의 **지금까지 관측한 활동 이력**을 한 문맥으로 삼는다.
문맥에는 선택된 객체 전부의 실제 객체 ID, 객체 유형, 순서가 있는 활동
이력이 들어간다. 아직 어떤 이벤트에도 참여하지 않은 객체도 빈 이력으로
포함된다. 객체 ID를 없애서 같은 유형의 이력을 서로 교환하지 않는다.

예를 들어 주문 O1의 이력이 `생성 → 포장`, 상품 I1의 이력이 `등록 → 포장`,
상품 I2의 이력이 `등록`인 상태는 세 객체의 전체 이력으로 구분한다.
O1과 I1의 토큰 수만 같다고 다른 객체 조합이나 다른 이력의 상태와 합치지
않는다.

이 문맥에서 비교할 행동은 **활동 + 실제 참여 객체 집합**이다.
`배송(O1, I1)`과 `배송(O1, I2)`는 다르다. 같은 객체 집합과 활동을 가진
서로 다른 transition은 행동의 수를 늘리지 않지만, 그 transition들이
도달하는 서로 다른 marking은 이후 문맥의 분석을 위해 모두 남긴다.

| 비교 대상 | 정확한 뜻 |
|---|---|
| 관측 행동 L(c) | 해당 문맥에서 객체별 관측 순서를 위반하지 않고 다음에 발생할 수 있는 로그 이벤트의 행동 집합 |
| 모델 행동 M(c) | 해당 관측 prefix를 synchronous move와 silent move만으로 재현하여 도달한 모든 marking에서 가능한 visible binding 행동의 합집합 |
| 일치 행동 I(c) | L(c)와 M(c)의 교집합 |
| 문맥 적합성 | `|I(c)| / |L(c)|` |
| 문맥 정밀도 | `|I(c)| / |M(c)|` |

이 모델 행동은 임의의 visible model move로 이탈한 뒤 돌아오는 행동을
포함하지 않는다. 이전 관측 행동을 어떤 marking에서도 재현할 수 없으면
이후 문맥의 M(c)는 빈 집합이다. 빈 집합의 분모에 임의로 0 또는 1을
부여하지 않고 `None`으로 남긴다. 반면 L(c)가 비어 있지 않고 M(c)가 비어
있으면 적합성은 정확히 0이다.

## 병행성, 공동 이벤트와 집계

로그 순서는 선택된 객체마다 선택된 E2O 관계를 모아 timestamp 순으로
정한다. 같은 객체에 timestamp 동률이 있으면 기본값 `reject`에서는
계산할 수 없다. 사용자가 `event_id`를 고르면 해당 동률에만 사전식 순서를
적용한다. 이는 인과관계의 증거가 아니다. 서로 객체를 공유하지 않는
이벤트 사이에는 timestamp가 달라도 추가적인 전역 선후관계를 넣지 않는다.

이 순서의 모든 downset, 즉 어느 이벤트를 포함할 때 그 선행 이벤트도
포함하는 관측 prefix를 열거한다. 서로 독립인 A와 B가 하나씩 있으면
`아무것도 전`, `A 후`, `B 후`, `A와 B 후`의 네 prefix가 있다.
마지막 것을 제외한 세 문맥을 평가한다. A 다음 B와 B 다음 A라는 두
선형화가 같은 prefix를 두 번 가중하지 않는다. 여러 객체가 공유하는
이벤트 역시 이벤트 하나로 이동한다.

고정된 로그에서 모든 평가 이벤트에는 참여 객체가 있고, 각 객체의 관측
순서는 고정되어 있다. 그러므로 전체 객체 이력의 길이들은 소비된 이벤트
집합을 식별한다. 구현은 이 전체 downset을 키로 사용하므로 hash 충돌이나
활동 라벨 중복으로 서로 다른 prefix를 합치지 않는다. `context_id`의
SHA-256은 증거 표시용이며, 계산의 상태 동등성 판정에 사용하지 않는다.

집계 방식 `micro_behavior_sets`는 모든 완료 문맥에서 교집합 크기를 더한
후 각각 관측 집합 크기의 합과 모델 집합 크기의 합으로 나눈다.
문맥별 비율의 단순 평균이나 이벤트 빈도 가중 평균과는 다른 수치다.
결과는 반올림된 실수 대신 `(분자, 분모)`로 저장한다.

예를 들어 관측이 `A → B`이고 처음 모델에서 A와 X가 가능하며 A 후에는
B만 가능하면, 전체 범위 적합성은 `2/2`, 정밀도는 `2/3`이다.
두 객체가 공동 참여한 A 한 번에 대해 모델이 A(o1), A(o2), A(o1,o2)를
허용한다면 적합성은 `1/1`, 정밀도는 `1/3`이다.

## 범위와 종료의 명시적 제외

`scope=selected_e2o_object_universe`,
`participant_policy=nonempty_selected`를 요청에 저장한다.
객체 유형과 qualifier를 선택한 뒤 참여 객체가 하나도 없는 로그 이벤트는
평가하지 않으며, `coverage.excluded_event_ids`와 issue에 반드시 기록한다.
모델에서도 실제 참여 객체가 없는 visible binding은 M(c)에서 제외한다.
이 선택은 의도한 범위 투영이며 자원 부족에 의한 `PARTIAL`과 구분한다.

모델의 **전체 구체 객체 universe**는 선택된 로그 객체들과 ID·유형이
일치해야 한다. 모델 marking을 몰래 자르거나 모델 객체를 새로 생성하지
않는다. 객체가 없는 유형이라도 모델 place의 유형이 선택 밖이면 거절한다.

`termination=excluded`이므로 다음 관측 이벤트가 없는 마지막 prefix는
평가하지 않는다. 마지막 관측 뒤 모델이 더 활동할 수 있거나 final marking에
아직 도달하지 못해도 이 점수만으로는 검사하지 않는다. 종료 적합성은
공동 OCPN alignment의 정확한 final marking 조건으로 별도로 확인한다.
전체 범위의 결과 이름은 `full_scope_*_ratio`이며, 원본 로그의 제외 이벤트까지
평가한 점수로 표현하면 안 된다.

## 탐색 한도와 해석

| 한도 | 중단 기준과 결과 |
|---|---|
| `max_log_states` | terminal을 포함한 서로 다른 관측 downset 수. 초과하면 전체 요청 문맥 수는 알 수 없으므로 `requested_contexts=None`, 모든 문맥 점수와 전체 점수를 비운다. |
| `max_context_states` | 한 문맥에서 서로 다른 구체 marking 수. 초기 후보 또는 silent closure가 초과하면 그 문맥과 관측상 이후 문맥을 미완료로 표시한다. |
| `max_bindings` | 방문 marking 하나에서 열거할 enabled binding 수. 정확한 후보 총수는 별도로 세고, 생략이 있으면 해당 문맥과 이후 문맥을 미완료로 표시한다. |

모델의 객체 ID universe가 유한해도 token multiplicity 때문에 reachable
marking 수는 무한할 수 있다. silent 생성 루프를 무조건 완료라고 선언하지
않는다. 한도를 정확히 채운 경우에는 추가 상태가 실제로 존재할 때만
미완료로 바뀐다.

`PARTIAL`이면 전체 범위 적합성·정밀도는 모두 `None`이다.
`complete_context_*`는 검증을 마친 일부 문맥만의 진단값이고 전체 점수를
대신하지 않는다. 미완료 문맥의 모델 행동 목록과 reachable marking 수는
발견한 부분만 나타낸다. `enabled_binding_candidate_count`는 방문한 각
marking에서 계산한 enabled binding 후보 수의 합으로, 한도로 생략한
후보도 포함하며 실제 생성한 행동 수와 다르다.

모든 계산 결과는 OCEL source digest, 모델 digest, 명시된 범위·가중치·한도와
계산 ID를 보존한다. 직접 로그와 모델을 입력하는 연산이므로 가상의 부모
계산 ID를 만들지 않는다.

## 기존 구현과의 관계 및 검증

확인한 OCPA snapshot은 `de056e0203a3fa4a9bbc19a95e001eada323074a`다.
해당 구현은 유형별 prefix multiset을 문맥으로 만들고 enabled activity
라벨을 비교하며 이벤트별 비율을 집계한다. 이 PIX 프로필은 전체 구체
객체 이력, 정확한 binding 행동, 모든 관측 downset, micro 집계를 명시한다.
두 정의의 점수 차이는 그 자체로 어느 한쪽의 구현 오류 증거가 아니다.
근거: [OCPA의 문맥 생성](https://github.com/ocpm/ocpa/blob/de056e0203a3fa4a9bbc19a95e001eada323074a/ocpa/algo/conformance/precision_and_fitness/utils.py),
[OCPA의 replay 및 점수 집계](https://github.com/ocpm/ocpa/blob/de056e0203a3fa4a9bbc19a95e001eada323074a/ocpa/algo/conformance/precision_and_fitness/variants/replay_context.py).

`tests/compute/test_object_context.py`는 순차·병행·공동 이벤트, 동일 라벨
분기, silent closure·cycle, binding cardinality, 객체 universe, qualifier,
동률, 빈 집합, 종료 제외, 탐색 한도와 결과 JSON 왕복을 검증한다.
독립 oracle는 작은 유한 상태 기계에서 모든 topological permutation과
객체별 토큰 위치를 직접 열거하며 PIX의 binding·firing·downset 함수를
재사용하지 않는다. `tests/compute/test_object_context_oracle.py`는 두 객체
유형의 유한 모델 400개와 한도 사례 1,200개에서 잘못된 완료 선언을 탐색한다.

JSON의 checksum이 맞아도 의미상 모순인 결과를 그대로 받아들이지 않는다.
계약은 문맥별 교집합·비율, 완료 문맥 집계, 범위별 개수의 균형을 확인한다.
미완료인데 전체 점수를 넣은 결과, 객체 순서만 바꿔 중복시킨 행동, 식별자만
바꿔 중복시킨 같은 prefix도 거절한다. 이는 저장된 증거끼리의 일관성
검사이며 원본 로그와 모델로 탐색을 다시 수행하는 검증은 아니다.

2026-09-10 실행에서 이 기능의 테스트 **1,697개**, 기존 import 경계 검사
5개가 통과했다. 실행 환경은 `.venv/Scripts/python.exe`이며, 보고서는
`.artifacts/object-context-tests.xml`에 저장했다. 네 Python 파일의 Ruff
검사와 포맷 검사도 통과했다. Python 3.10 인터프리터는 실행 전에 Windows
Application Control 정책으로 차단되어 이 신규 기능의 3.10 실행 결과는
확인하지 못했다. 정책을 우회하지 않았다.

검토 기준일은 2026-09-10이다. 정의 변경, 한도 관련 오분류, 독립 oracle와
다른 문맥·행동 집합을 만드는 반례가 발견되면 해당 정확성 판단을 철회하고
재검증한다. 임의의 대형 로그에 대한 실행 시간·메모리 사용량과 OCPA보다
빠른지 여부는 **알 수 없음**이다. 유한 예제 통과를 대규모 성능이나 모든
OCPN에 대한 종료 증명으로 확장하지 않는다.
