# Case-Centric / Object-Centric 계산 사용

이 안내는 2026-09-15의 미출시 작업본에 해당한다. 계산별 참조 대응 범위와 남은 차이는
[합집합 구현 문서](../requirements/2026-09-15_PIX_NATIVE_MINING_UNION.md)와
[행별 registry](../requirements/union-2026-09-15/implementation_registry.json)에 기록한다.
함수가 존재한다는 사실과 모든 참조 variant의 대체 검증은 구분한다.

## 입력과 계산 경계

| 입력 | 공개 진입점 | 보존하는 의미 |
|---|---|---|
| XES/MXML 또는 명시적으로 매핑한 case 로그 | `pix.case_centric` | Case ID, 이벤트의 원본 순서, classifier, global 속성 |
| Canonical OCEL | `pix.object_centric` | 공유 이벤트, 객체형, E2O/O2O 방향과 qualifier, 객체 속성 이력 |
| 이미 계산한 trace/model/result | 해당 계산 모듈의 명시적 입력 계약 | 원본·부모 계산 ID, 모델 digest, 계산 설정 |

`read_log()`는 XES를 `CaseLog`로, OCEL을 `OCEL`로 읽는다. Object-Centric 계산을
Case-Centric 계산으로 바꾸려면 객체형·qualifier·동시각 정책을 선택해 trace를 투영해야 한다.
투영된 두 trace에 나타나는 공유 이벤트를 전체 이벤트 수로 합산하면 중복된다.

## Case-Centric 예

```python
from pix import case_centric as cc
from pix.api import process_tree_to_petri_net
from pix.event_log import CaseLog
from pix.io import read_log

log = read_log("process.xes.gz")
if not isinstance(log, CaseLog):
    raise TypeError("CaseLog input required")

dfg = cc.discover_dfg(log)
discovered = cc.discover_inductive(log)
if discovered.value is None:
    raise ValueError(discovered.issues)

net = process_tree_to_petri_net(discovered.value)
alignment = cc.align_traces(log, net)
print(alignment.status, alignment.issues)
```

탐색 설정과 계산 정의는 각 하위 모듈에서 고른다. 예를 들어
`cc.inductive.InductiveSpec(variant="imf", noise_threshold=0.2)`는 빈도를 보존하는
IMf 경로를 선택한다. `cc.alignment_search`, `cc.approximate_alignment`,
`cc.tree_alignment`는 서로 다른 정렬 계산을 제공한다.
`cc.conformance`의 지표와 `cc.evaluation`의 집계는 모집단·분모·누락 정책을 함께 기록한다.

## Object-Centric 예

```python
from pix import object_centric as oc
from pix.io import read_log
from pix.ocel import OCEL

log = read_log("process.json")
if not isinstance(log, OCEL):
    raise TypeError("OCEL input required")

context = oc.ComputationContext(log)
census = oc.object_statistics(context)
relations = oc.discover_object_graph(context)
order_traces = oc.reconstruct_traces(
    context, oc.TraceSpec(object_type="Order")
)
```

`oc.conformance`는 joint object replay와 flattened replay를 구분한다.
`oc.performance`도 EOG 선행 이벤트 시각과 replay token의 도착 시각을 구분한다.
Waiting·sojourn·flow 등의 이름만 보고 두 계산 결과를 서로 교환하면 안 된다.

## 결과 읽기와 보존

```python
from pix.results import result_json_bytes, result_from_json

encoded = result_json_bytes(dfg)
restored = result_from_json(encoded)
assert restored == dfg
```

결과에는 `operator_id`, `spec`, `source_digest`, `parent_computation_ids`, `status`,
`value`, `issues`가 있다. `computed`는 선택한 계산 정의에 대한 완료이며 업무 규칙의
승인이나 미래 실행 성공을 의미하지 않는다. `partial`은 알려진 부분과 불확실한 범위를
함께 읽어야 한다. `unavailable`·`invalid_input`은 숫자 0이나 부적합으로 바꾸지 않는다.

필터·변환 결과는 선택 또는 변경 계획과 근거를 담는다. 실제 로그는 해당 모듈의
`materialize_*` 함수로 얻는다. 이 함수는 원본 digest와 요청·근거의 일치를 확인한다.
역변환에 필요한 source sidecar는 별도로 보관한다. 분석 결과 JSON만으로 원본의
삭제된 정보나 모든 원본 파일 표현을 복원할 수 있다고 가정하지 않는다.

## 검증 범위

위 Case/OC 흐름은 `tests/test_mining_union.py` 및 격리 wheel 검증 도구의 시나리오에
대응한다. 모듈별 실제 결과 저장·복원은 `tests/test_mining_serialization.py`에서 검사한다.
실제 로컬 XES/OCEL 데이터의 원본 대조 결과는 합집합 구현 문서의 검증 기록을 참조한다.

기본 계산은 PM4Py·OCPA를 실행하지 않는다. 선택적인 SciPy 경로와 로컬 Transformer
모델 경로는 필요한 runtime과 모델이 있어야 하며, 이번 native 테스트와 동일한 검증 범위로
집계하지 않는다. Privacy 계산의 일반 진단 결과에는 비공개 원본 참조가 남을 수 있으므로
각 모듈의 공개용 결과 계약과 보장 범위를 따른다. 특히 PRIPEL 진단을 공개 인증 결과로
취급하지 않는다.
