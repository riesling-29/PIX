# PIX enabled-prefix precision v1

이 문서는 `pix.enabled_prefix_precision.v1`의 계산 정의와 검증 범위를 고정한다. 이 지표는 classical object trace와 accepting Petri net을 입력으로 받으며, OCPN context precision이나 PM4Py Align-ET와 동일한 지표라는 주장은 하지 않는다. 검토 기준일은 2026-09-10이다.

## 입력과 의미

로그에서 객체 유형 하나를 선택해 만든 `TraceSet`의 활동 순서를 사용한다. 같은 사건을 공유하는 두 객체의 trace는 서로 다른 trace 발생으로 센다. 추적 대상은 활동명으로 이루어진 **전체 prefix**다. DFG의 직전 활동 쌍으로 대체하지 않는다.

초기 marking에서 prefix `p`의 활동들을 순서대로 정확하게 실행한 뒤, silent transition만으로 더 이동해 도달할 수 있는 **모든** marking의 집합을 `R(p)`로 정의한다. Visible model move와 log move는 허용하지 않는다. 같은 활동명을 가진 여러 transition과 모든 silent 분기를 유지한다. `M(p)`는 이 marking들 중 어디에서든 실행 가능한 visible 활동명의 합집합이고, `O(p)`는 로그에서 그 prefix 바로 다음에 실제 관측된 활동명의 집합이다. 같은 활동명을 가진 transition이 여러 개여도 선택지 수는 한 개다.

`M(p)`에는 이후 final marking에 도달하지 못하는 경로의 활동도 포함된다. 따라서 이 지표는 **실행 가능한 prefix의 선택지**를 측정하며, 모델의 수용 언어만을 대상으로 하는 precision이나 soundness를 증명하지 않는다.

## 종료와 발생 가중치

호출자는 `PrefixPrecisionSpec(terminal_policy="include")` 또는 `"exclude"`를 반드시 선택한다. 숨겨진 종료 정책은 없다.

| 정책 | prefix의 가중치 | 모델 종료 선택지 | 로그 종료 관측 |
|---|---|---|---|
| `include` | 해당 prefix에 도달한 trace 발생 수 | `R(p)`에 정확한 final marking이 하나라도 있으면 true | 그 prefix에서 끝난 trace가 하나라도 있으면 true |
| `exclude` | 해당 prefix 이후 관측 사건이 남아 있는 trace 발생 수 | 선택지에 포함하지 않음 | 관측 선택지에 포함하지 않음 |

종료는 별도의 boolean이다. `"END"` 같은 실제 활동 문자열과 충돌하는 sentinel을 사용하지 않는다. Final marking에서도 visible 활동을 실행할 수 있으면 종료와 해당 활동이 동시에 선택지가 된다.

예를 들어 로그가 `A`, `AB`이면 prefix `A`의 방문 수는 2, 연장 수는 1, 완료 수는 1이다. 가중치는 포함 모드에서 2, 제외 모드에서 1이다. 제외 모드에서는 최종 prefix가 가중치 0이므로 `excluded_terminal_policy`로 기록한다.

## 정수 계산식

각 prefix의 모델 선택지 수 `m(p)`는 `|M(p)|`에 정책에 따른 모델 종료 boolean을 더한 값이다. Escaping 선택지 수 `e(p)`는 `|M(p) − O(p)|`에 “모델에서는 종료할 수 있지만 로그에서는 그 prefix의 종료를 관측하지 않았다”는 boolean을 더한 값이다.

계산 가능한 prefix 집합을 `C`, 각 prefix의 발생 가중치를 `w(p)`라고 하면 다음 정수 합을 저장한다.

```text
D = sum(w(p) × m(p), p in C)
N = sum(w(p) × (m(p) − e(p)), p in C)
completed_ratio = (N, D)
```

유리수를 부동소수점으로 바꾸거나 약분해 발생 수를 감추지 않는다. 전체 대상 prefix가 계산된 경우에만 `whole_log_ratio`에 같은 비율을 기록한다. 부분 집합의 비율을 전체 로그 점수로 제시하지 않는다.

관측 사건 발생이 하나도 없거나 `D=0`이면 점수는 **알 수 없음**이다. 두 ratio는 `None`, `metric_status`는 `unavailable`이다. Empty trace만 존재하고 초기 marking이 final marking인 경우에도 관측 사건이 없다는 이 profile의 명시적 정책을 적용한다. 이때도 coverage와 prefix 근거를 보존하기 위해 계산 결과 envelope는 `computed`일 수 있다. “근거 계산 완료”와 “지표값 존재”는 별도 상태다.

## 비적합과 탐색 제한

Prefix 자체를 정확하게 실행할 수 없으면 `unfit_prefix`다. Prefix는 실행 가능하지만 관측 다음 활동 또는 포함 정책의 종료 관측을 재현할 수 없으면 `unfit_observation`이다. 이 prefix의 가중치를 부분 점수에서 제외한다. 원래 prefix의 정확한 marking 집합은 남아 있으므로 계산 가능한 다른 자손까지 무조건 제외하지 않는다.

`max_markings_per_prefix`는 각 prefix의 closure에 포함되는 서로 다른 marking 수를 제한한다. 초기 seed도 포함한다. Closure 크기가 제한과 같더라도 모든 후속 marking이 이미 방문된 집합 안에 있으면 정상 완료한다. 추가 marking 하나가 발견될 때 제한 도달로 판정한다. Silent self-loop의 반복 발화 횟수를 새로운 marking으로 세지 않는다.

제한으로 전체 집합을 알 수 없는 prefix는 `search_limit`, 그 집합에 의존하는 자손은 `upstream_search_limit`로 기록한다. 부분 탐색에서 본 enabled 활동을 완전한 `M(p)`라고 보고하지 않으며, 알 수 없는 marking·enabled·escaping 필드는 `None`이다. 비적합 또는 탐색 제한이 하나라도 있으면 envelope는 `partial`이고 전체 로그 점수는 없다.

## 눈으로 검토할 반례

아래 비율은 이해를 위해 약분한 값이다. 저장 결과는 원래 정수 합을 유지한다.

| 모델과 로그 | 종료 포함 | 종료 제외 | 확인하는 성질 |
|---|---:|---:|---|
| 모델 `A`, 로그 `A` | 1 | 1 | 정확 일치 |
| `A` 뒤 `B` 또는 `C`, 로그 `AB` | 3/4 | 2/3 | 같은 활동의 모든 후속 marking 합집합 |
| `A` 후 final에서 `B`, `C` self-loop, 로그 `A`, `AB` | 7/11 | 3/4 | 종료 발생과 연장 발생의 가중치 구분 |
| `A` 후 final에서 `B`도 가능, 로그 `A` | 2/3 | 1 | 추가 실행과 종료 관측의 구분 |
| 모델 `AB`, 로그 `A` | 부분 결과, 전체 점수 없음 | 1 | 제외 모드의 점수는 accepting fitness가 아님 |
| 초기 `A→final` 또는 `X→dead-end`, 로그 `A` | 2/3 | 1/2 | dead-end의 실행 가능한 선택지도 계산 |
| 초기/최종이 같고 `A` self-loop, 로그 `AA` | 1/2 | 1 | 제외 정책이 종료 시점 차이를 측정하지 않음 |
| 같은 DFG를 가진 `ABACA`와 `ACABA`, 첫 순서만 허용하는 모델 | 첫 로그만 전체 점수 1 | 첫 로그만 전체 점수 1 | DFG가 같아도 전체 prefix는 다름 |
| 무한히 token을 늘릴 수 있는 silent transition | 제한 근거, 전체 점수 없음 | 제한 근거, 전체 점수 없음 | 탐색 한계를 적합성 판단으로 바꾸지 않음 |

## 구현·검증과 판단 범위

계약은 `src/pix/contracts/precision.py`, 계산은 `src/pix/compute/precision.py`, 저장된 회귀 시험은 `tests/compute/test_precision.py`에 있다. 시험에는 알려진 작은 정답, 종료 문자열 충돌, 중복 활동 transition, silent cycle, 정확한 cap 경계, 비적합 분기, 빈 사건 모집단, 같은 DFG의 다른 prefix, 그리고 PIX의 발화 함수를 호출하지 않는 유한 상태 그래프 oracle이 포함된다.

Python 3.11에서 precision 시험 155개와 import 경계 시험 5개를 통과했다. Ruff 검사와 변경 파일 포맷 검사도 통과했다. 추가 회귀 시험은 실제 동시간 사건의 정렬 경고 보존, 부분 결과에 전체 점수를 끼워 넣은 모순, 재서명한 JSON의 잘못된 coverage·분모·가중치 거부를 포함한다. 계약 검증은 저장된 근거 사이의 산술·집합·모집단 일관성을 검사하며 모델 탐색을 재실행하지 않는다. 별도 검토자가 유한 상태 그래프 oracle로 300개 seeded net의 두 종료 정책과 여러 cap을 조합한 2,030회 실행을 확인했으나, 이 추가 실행은 저장된 pytest 수에 포함하지 않는다. Python 3.10 재검증은 현재 `.artifacts/py310/Scripts/python.exe` 실행을 Windows Application Control 정책이 차단하여 수행하지 못했다. 최종 통합 시험 결과는 버전 구현 기록을 따른다.

이 판단은 이 profile, 현재 코드, 기록된 시험 범위에 한정한다. 위 작은 정답을 재현하지 못하거나 실제 결과가 종료·가중치·coverage 정의와 다르면 해당 판단을 철회하고 재검토한다. 무한 상태 공간의 일반 종료성, 대용량 성능, 기존 precision 구현 대비 우위는 **알 수 없음**이다. 정의 또는 구현이 변경되거나 반례가 확인되는 시점까지 이 설명이 유효하다.
