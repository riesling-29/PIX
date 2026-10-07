# PIX 공동 OCPN alignment 구현 프로파일

기준일: 2026-09-10. 이 문서는 `pix.align_object_log`의 구현된 계산 의미와 검증 범위를 설명한다. 객체형별 classical alignment는 기존 `pix.align_traces`에 남으며, 아래 연산자는 구체적인 객체들의 공동 실행을 계산한다.

## 무엇을 하나의 입력으로 보는가

현재 지원하는 scope는 명시적인 `whole_log` 하나다. 원본 OCEL의 **모든 event를 한 번씩** 처리한다. 분석할 객체형과 E2O qualifier를 선택하며, 선택 이후 참여 객체가 0개가 된 event도 유지한다. 이벤트를 자동으로 execution으로 나누거나, 하나의 공유 event를 객체형별로 복제하지 않는다.

선택한 객체는 고립 객체까지 포함한다. 모델의 유한 객체 목록은 이 선택과 ID·유형이 정확히 같아야 한다. 모델의 초기·최종 marking을 분석 대상에 맞춰 자동으로 잘라내지 않는다. 누락 객체, 추가 모델 객체, 서로 다른 객체형 지정, 선택 밖 모델 place 유형은 입력 문제로 반환한다. 따라서 빈 이벤트 로그라도 고립 객체에 대한 모델 완료가 필요할 수 있다.

다른 객체형이나 qualifier의 관계를 제외한 수는 결과 scope에 남긴다. 원본 OCEL과 canonical identity는 수정하지 않는다. 모델은 외부 규범 모델이나 PIX에서 발견한 모델 모두 가능하며, 로그의 canonical digest와 모델의 semantic digest를 함께 계산 identity에 포함한다.

## 순서는 객체별 선행 관계다

각 선택 객체에 연결된 event들을 기록 시각으로 정렬하여 인접 선행 관계를 만든다. 서로 다른 객체를 다루고 선택된 공유 객체가 없는 두 event 사이에는, 시각이 다르더라도 전체 순서를 강제하지 않는다. 모델이 요구하는 순서에 따라 두 event의 순서를 교환할 수 있다.

| 상황 | 처리 |
|---|---|
| 같은 선택 객체에서 서로 다른 시각 | 앞 event를 처리한 뒤 다음 event를 처리 |
| 같은 선택 객체에서 동일 시각 | 기본은 `unavailable`; `event_id` 정책을 명시하면 ID 순으로 순서 부여 |
| 선택 객체를 공유하지 않는 event | 서로 독립적으로 처리 가능 |
| 여러 객체가 공유하는 event | 모든 선행 조건을 만족해야 하며 event 자체는 한 번만 처리 |
| 선택된 참여 객체가 없는 event | 선택 객체 기준 선행 제약 없이 한 번 처리 |

`event_id`는 동시 기록을 해석하기 위한 명시적인 관례이며 인과 증거가 아니다. 실제로 같은 선택 객체에서 동시각을 처리한 경우에만 `timestamp_tie_broken` 진단과 해당 객체·event 쌍을 반환한다. 이 정보 진단 때문에 완료된 계산을 부분 계산으로 바꾸지는 않는다. 이 구현은 O2O나 속성에 근거한 추가 인과 제약을 추론하지 않는다.

## Synchronous move의 조건

로그 event와 모델 transition의 activity identity가 같아야 한다. 이때 모델 binding의 **구체적인 참여 객체 집합**도 선택된 E2O 참여 집합과 정확히 같아야 한다. 같은 유형의 다른 객체로 대체하거나, 공동 event의 일부 객체만 소비하는 synchronous move는 허용하지 않는다.

여러 qualifier로 같은 event·object가 연결되어도 참여 객체는 한 번 센다. 해당 qualifier 근거는 모두 보존한다. 모델이 요구하는 빈 type 그룹은 binding 안에 유지하지만 비교할 때 빈 그룹 자체는 참여로 세지 않는다. 0개 참여는 해당 arc의 명시적인 최소 cardinality가 0이거나, transition에 그 type의 incidence가 없을 때만 가능하다.

| 모델 arc 제약 | A event 참여 객체 | 처리 예 |
|---|---|---|
| T 객체 정확히 1개 | T 객체 a·b | 이 event를 a만 골라 synchronous 처리할 수 없음 |
| T 객체 1–2개 | T 객체 a·b | 두 객체가 필요한 모든 input place에서 활성화되면 공동 처리 가능 |
| T 객체 0개 허용 | 참여 없음 | 빈 binding이 가능하면 synchronous 처리 가능 |

동일 활동명을 가진 서로 다른 transition ID는 별도 후보로 남긴다.

## 객체형별 적합성이 공동 적합성을 보장하지 않는 반례

X 객체 x와 Y 객체 y가 A event 하나를 공유한다고 하자. 같은 활동명 A를 가진 transition 두 개가 다음처럼 동작한다.

| A의 선택 | X의 도착 상태 | Y의 도착 상태 |
|---|---|---|
| t0 | 최종 상태 | 추가 작업 필요 |
| t1 | 추가 작업 필요 | 최종 상태 |

X만 보면 t0로 A를 설명할 수 있고, Y만 보면 t1로 A를 설명할 수 있다. 그러나 하나의 공유 event에서 t0와 t1을 동시에 선택할 수 없다. 둘을 공동으로 완료하려면 한쪽의 추가 모델 작업이 필요하다.

영구 시험은 이 반례에서 객체형별로 다른 A transition이 적합함을 확인하고, 공동 alignment의 최소 model deviation 비용이 1임을 별도의 유한 그래프 계산과 비교한다. 이 차이를 감추는 객체형별 비용 합산은 사용하지 않는다.

## 비용과 해석

Log·visible model·silent·synchronous move의 기본 비용은 각각 명시적인 비음수 정수다. 기본값은 1·1·0·0이다. 두 가중 방식이 있다.

| 비용 방식 | 각 move의 비용 |
|---|---|
| `event` | 해당 종류의 기본 비용 × 1 |
| `object` | 해당 종류의 기본 비용 × 서로 다른 참여 객체 수 |

`object` 방식에서 0개 참여의 가중치는 **0**이다. 자동으로 1로 올리지 않는다. 이 때문에 미등록 활동의 객체 없는 log move도 비용이 0일 수 있다. 사용자가 기본 비용을 0으로 선택할 수도 있다. 따라서 비용 0을 fitness 1 또는 deviation 없음으로 해석하지 않는다. 결과는 synchronous·silent·model·log move 수와 경로를 별도로 제공한다. 정규화 fitness는 이 연산자의 출력에 포함하지 않는다.

## 탐색 상태와 완료의 의미

탐색 상태는 이미 처리한 event 집합과 모델 전체의 구체적 object marking이다. 이미 처리한 집합은 위 선행 관계의 조건을 만족한다. 초기 marking에서 시작하여 모든 event를 처리하고 **최종 marking과 정확히 같아지는** 상태를 찾는다. 남은 추가 token도 최종 판정에 영향을 준다.

비음수 비용의 Dijkstra 탐색으로 최소 비용의 경로 하나를 구한다. 목표를 처음 생성했을 때가 아니라 최소 비용 상태로 확정했을 때 최적이라고 반환한다. 같은 비용의 모든 경로를 열거하지 않는다.

모델 binding 후보는 모델에 선언한 유한 객체 집합에서만 만든다. input place가 여러 개라면 같은 객체가 필요한 모든 place에서 사용 가능해야 한다. 반복 token은 marking의 multiplicity로 남지만 같은 객체 집합의 binding을 중복 후보로 만들지 않는다. 모델의 source transition이 object token을 계속 생성할 수 있으므로, 유한 객체 ID 목록이 유한 상태 공간을 뜻하지는 않는다.

| 상태 | 근거와 출력 |
|---|---|
| `optimal` | 최소 비용 목표를 확정. 전체 경로·비용·move 수 제공 |
| `unreachable` | 유한 탐색 frontier가 완전히 소진. 허용 경로가 없다는 결과이며 비용 없음 |
| `search_limit` | 확정 상태 수 한도 도달. 결과 envelope는 `partial`, 경로·최소 비용 확정 없음 |
| `binding_limit` | 한 marking의 전체 enabled binding 수가 별도 한도를 초과. 결과 envelope는 `partial` |

Binding을 일부만 열거한 경우, 그중 목표로 가는 후보가 있어도 최적 경로로 발표하지 않는다. 비용 하한과 정확한 enabled binding 수를 남긴다. 전체 binding 집합이 한도와 정확히 같으면 잘린 탐색이 아니다. 한도는 결과 identity에 포함한다.

## 구현과 영구 시험

- [계산 및 공통 scope 준비](../../src/pix/compute/object_conformance.py)
- [불변 결과 계약](../../src/pix/contracts/object_conformance.py)
- [유한 binding 열거](../../src/pix/compute/object_bindings.py)
- [scope·참여·순서·한도 회귀 시험](../../tests/compute/test_object_conformance.py)
- [독립 유한 그래프 Bellman–Ford oracle](../../tests/compute/test_object_alignment_oracle.py)
- [binding 조합·완전성·큰 조합 수 시험](../../tests/compute/test_object_bindings.py)

검증에서 Python 3.11로 이 구성요소의 256개 시험과 71개 subtest가 통과했다. 독립 oracle은 고정 seed의 유한 공동 모델 192건과 상태 한도 384건을 포함하며, 제품 firing·binding·탐색 내부 함수를 사용하지 않고 기대 비용과 실제 경로를 검사한다. Binding 시험에는 2^160개의 가능 binding을 실제로 전부 생성하지 않고 정확히 세는 사례도 있다. 이 숫자는 해당 시험 명령의 결과이며 최대 로그 규모나 실사용 성공률이 아니다.

객체 15,000개의 선택적 참여로 2^15000개의 후보가 생기는 실제 계산도 포함한다. Binding 한도 1에서 반환된 `binding_limit` 결과의 정확한 후보 수를 analysis-result 1.1.0 형식으로 저장·재입력하여 동일성을 확인한다. 거대한 수는 손실 없는 명시적 16진수 표기로 보존하며 Python의 전역 정수 변환 한도를 바꾸지 않는다. 이 시험은 거대한 **계산 결과의 후보 수** 보존을 확인한 것으로, 모든 크기의 사용자 지정 비용이나 모델 입력 정수가 지원된다는 검증은 아니다.

현재 구현의 Python 3.10 전체 검증, 대규모 로그의 처리량·최대 규모·완료 시간은 **알 수 없음**이다. 현재 프로파일은 unit-incidence OCPN, 명시적인 유한 객체 ID, 선택된 E2O 선행 관계와 위 비용 정의에 유효하다. 추가 lifecycle·O2O 인과 제약이나 다른 binding 의미가 필요하면 별도 프로파일로 다루어야 한다. 순서·participation·비용의 반례가 이 정의와 충돌하면 해당 계산을 수정하고 검증 근거를 갱신한다.

이 구현은 객체형별 설명을 합산하는 수준을 넘어, 선택한 전체 로그의 사건들과 구체적인 객체들을 하나의 모델 실행 경로에서 일관되게 설명하는 첫 공동 alignment 프로파일이다.
