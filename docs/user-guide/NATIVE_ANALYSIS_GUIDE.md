# PIX 자체 분석·모델·그래프 사용 안내

기준: PIX 0.4.0. PM4Py·OCPA를 설치하거나 호출하지 않는 자체 구현이다.
Python 계산은 표준 라이브러리만 사용하고, 그래프 HTML에는 고정 버전 ELK가 포함된다.

## 실제 연결되는 경로

OCEL 입력 → 의미 검증·정규화 → 객체별 Trace/OCDFG/Execution → 모델 발견 또는
통계 → 모델 실행·적합성 검사 → 결과/모델 JSON과 그래프 HTML.
Canonical V1은 계속 원본 로그 동일성의 기준이며, 분석 조건·화면 좌표와 구분한다.

| 단계 | 제공 API | 의미와 경계 |
|---|---|---|
| 로그 교환 | `read_ocel`, `import_ocel`, `export_ocel` | JSON/XML/SQLite; JSON/XML gzip; 출력 후 재입력 digest 검증 |
| 객체 Trace | `reconstruct_traces` | qualifier 선택, 공유 event 중복 제거, 고립 객체 보존 |
| 관계 통계 | `discover_dfg`, `discover_ocdfg` | 객체형별 event pair·고유 객체·발생 건수의 구분 |
| 시간 | `measure_temporal` | 관측 시각 간격; 명시한 시작 속성의 service time; microsecond와 정확한 sum/count |
| Execution | `discover_executions` | 연결성 또는 유형별 최단 탐색 깊이의 leading object; 중첩·경계 밖 참조·미소속 표시 |
| Variant | `discover_variants` | 객체 이름을 일관되게 바꾸어도 유지되는 incidence 동형; 한도 초과는 unavailable |
| Classical 발견 | `discover_process_tree` | `pix.inductive_cut.v1`과 명시적 log-based `pix.im.v1`; IMf/IMd는 미지원 |
| OCPN 발견 | `discover_ocpn` | 객체형별 native 발견·명시적 전이 병합·관측 참여 분포·검증된 로그 수락 경로 |
| 실행 모델 | `process_tree_to_petri_net`, `fire`, `fire_binding` | Petri net과 명시적 OCPN 객체 binding의 활성화·발화·종료 판정 |
| 적합성 | `align_traces`, `replay_traces` | Classical Petri net에 대한 객체별 Trace; 비용·token·탐색 범위 공개 |
| 공동 적합성 | `align_object_log`, `enumerate_enabled_bindings` | 공유 event를 한 번 소비하는 bounded OCPN alignment; 구체 binding·객체별 부분순서 |
| Prefix precision | `measure_prefix_precision` | 종료 포함/제외 정책 필수; 가능한 모든 prefix marking과 정수 분자·분모 |
| Object context | `measure_object_context` | 구체 객체 이력과 activity+참여 객체 행동을 비교하는 별도 fitness/precision |
| 업무 규칙 | `evaluate_constraints` | Count·Response·Precedence·NotCoexistence·TimedResponse; open/closed 관측과 pending 구분 |
| 결과 교환 | `write_result`, `read_result` | 모델/로그와 별도인 버전 지정 결과; 부모 계산·요청·문서 digest 확인 |
| 모델 교환 | `write_model`, `read_model` | PIX 모델 형식; 발견/외부 제공 출처를 보존; PNML/BPMN을 표방하지 않음 |
| 그래프 | `build_graph`, `build_model_graph`, `export_html` | DFG/OCDFG와 Petri net/OCPN의 offline SVG 탐색; 필터는 원본 계산을 변경하지 않음 |

## 최소 계산 예시

```python
from pix.api import OCDFGSpec, TraceSpec, discover_ocdfg, read_ocel, reconstruct_traces
from pix.viewer import build_graph, export_html

log = read_ocel("orders.json")
traces = reconstruct_traces(log, TraceSpec("Order"))
result = discover_ocdfg(log, OCDFGSpec(("Order", "Package")))
if result.status.value == "computed":
    export_html(build_graph(result), "process.html")
```

같은 객체의 선택된 event가 동일 시각이면 Trace 기본 정책은 순서 판단을 유보한다.
`tie_policy="event_id"`는 명시적으로 선택한 ID 사전식 순서이며 인과관계의 증거가 아니다.
Execution 연결성 추출은 완료되어도 그 안의 순서 그래프는 unavailable일 수 있다.
그 입력으로 exact variant를 완료한 것처럼 표시하지 않는다.

## 모델과 적합성

```python
from pix.api import AlignmentSpec, DiscoverySpec, align_traces
from pix.api import discover_process_tree, process_tree_to_petri_net

tree = discover_process_tree(traces, DiscoverySpec(algorithm="pix.im.v1"))
if tree.status.value == "computed":
    net = process_tree_to_petri_net(tree.value)
    alignment = align_traces(traces, net, AlignmentSpec(max_states=10000))
```

두 miner는 trace 입력을 사용하며 DFG로 자동 축소하지 않는다. 발견된 tree의
허용 언어는 관측 로그보다 넓을 수 있다. Flower fallback이 쓰였으면 issues에 남긴다.
`noise_threshold=0`만 지원하며 다른 값이나 미등록 miner 이름은 거절한다.
`pix.im.v1`의 formal cut·split·fallthrough 정의는
[IM profile 명세](../architecture/5_PIX_LOG_BASED_INDUCTIVE_MINER.md)에 있다.
기존 기본값 `pix.inductive_cut.v1`을 조용히 다른 발견 정책으로 바꾸지 않았다.

Alignment는 명시한 정수 비용에서 Dijkstra 탐색으로 최소 비용 경로 하나를 구한다.
전체 탐색이 끝나지 않으면 `PARTIAL`이며 완료 표본의 합·분모와 한도 초과 수를 구분한다.
Token replay는 별도의 결정적 국소 정책으로 missing/remaining/consumed/produced를
제공한다. 두 결과에 정규화 fitness라는 이름을 붙이지 않는다.

OCPN 실행은 같은 event에 참여할 구체 객체 binding의 가능성을 검사한다.
고정 arc는 정확히 하나, variable arc는 명시한 최소·최대 참여 수를 따른다.
현재 OCPN 모델에는 구체 객체 universe와 initial/final object marking이 포함된다.
Binding 열거와 공동 alignment는 명시한 유한 객체 universe에서 탐색한다.
자동 객체 생성 의미는 지원하지 않는다. OCPN 발견은 관측 로그의 수락 경로를 확인하지만
공동 soundness를 인증하지 않는다. 한 유형 안의 중복 activity 전이는 임의로 합치지 않는다.

새 평가 구조와 모집단·반증 조건은
[모델 발견·공동 실행·평가 안내](NATIVE_MODEL_EVALUATION_GUIDE.md)에 설명했다.

모델 화면은 place·visible/silent transition, 초기/종료 marking, 고정/가변 arc를
구분한다. OCPN variable arc의 점선과 참여 수는 빈도를 뜻하지 않는다. 같은 활동명을
가진 transition도 개별 ID를 유지한다. 선택한 노드·arc의 객체, 제약과 모델 출처는
오른쪽 inspector에서 확인한다.

`Fit`은 전체 구조를 보여주며 긴 모델에서는 글자가 작아질 수 있다. `Readable`은
선택 영역을 설계된 글자 크기로 확대하고, 이동하며 나머지를 살필 수 있게 한다.
필터를 바꾸어도 기존 배치와 원본 데이터는 유지된다. 브라우저에서 정확한 정수로
표시할 수 없는 `2**53 - 1` 초과 크기의 값은 HTML 생성 시 거절한다. Python 계약은
큰 정수를 정확히 보존한다. 모델 JSON 1.0의 numeric literal은 Python의 정수 문자열
변환 제한을 적용받으므로 그 제한을 넘는 값의 저장까지 보장하지 않는다.

## 데이터 보존과 실패

`computed`, `partial`, `unavailable`, `invalid_input`을 구분한다. 요청한 service time에
start 속성 누락이 있으면 coverage와 issues를 남긴다. 시작 속성을 선택하지 않은 기본
gap 계산은 간격만 계산하고 service를 unavailable로 표시한다. 숫자 0으로 대체하지 않는다.

입출력은 기존 파일을 기본적으로 덮어쓰지 않는다. `overwrite=True`를 명시하면 교체한다.
`write_result`와 `write_model`은 path·byte_count·output_sha256·cleanup_issues가 있는
출판 결과를 반환한다. 이 객체 자체를 `read_result`/`read_model`의 경로로 사용할 수 있다.
출력 게시 후 임시 파일 정리에 실패해도 게시 성공은 유지하고 정리 문제를 별도 보고한다.
Viewer의 `export_html`은 편의용 `Path`를 반환한다. 동일한 파일 hash·크기·정리 진단이
필요한 호출자는 `export_html_report`의 구조화된 반환값을 사용한다.

XML은 명시한 무namespace 구조 profile이다. 공식 XSD 검증 상태를 성공으로 표시하지 않는다.
SQLite의 정수 범위, negative zero, 예약 열 충돌처럼 의미 보존이 불가능한 값은 거절한다.
결과/모델 문서 digest는 변조·손상 감지용이며 서명이나 계산 결과의 진실성 증명이 아니다.
분석 결과 형식 1.1은 1.0 문서 읽기를 유지하고 4096 bit를 넘는 결과 정수를
`{"$pix.integer.hex": "0x..."}` 형태로 보존한다. 전역 Python 정수 변환 제한을 바꾸지 않는다.
큰 binding 수의 결과 저장을 지원하는 변경이며, 임의 크기 요청 매개변수·모델 digest의
정수 입력 범위를 확대했다는 뜻은 아니다. 요청·payload의 모델·정책·부모·상태 모순도 검사한다.

## 직접 확인할 예제와 테스트

```shell
python examples/native_pipeline.py --output .artifacts/native-demo
python examples/model_evaluation.py --output .artifacts/v040/demo
python -m pytest -q
```

예제는 실제 계산을 거쳐 원본 OCEL 세 형식, 실행·variant·시간·모델·alignment 결과,
관측 OCDFG인 `process.html`과 발견한 Petri net인 `model.html`을 만든다.
`ocpn.html`은 입력 로그와 독립적으로 제공한 공동 배송 OCPN 예제다. 이를 자동 발견한
모델로 표시하지 않으며, `provided-ocpn.json`에 해당 출처를 기록한다.
생성된 HTML은 네트워크 없이 열 수 있다. 동일 경로를 재사용할
경우에만 `--overwrite`를 명시한다. 단계별 시험은 `tests/ocel`, `tests/compute`,
`tests/viewer`, `tests/browser` 및 최상위 통합 시험에 나누어 있다.

두 번째 예제는 실제 OCPN 발견, 공동 alignment, 두 종료 정책의 precision, object context,
열린/닫힌 규칙과 domain 검토용 `review.md`를 생성한다. 발견 OCPN과 각 발화의 객체·비용,
참여 수 분포, 9분 배송 규칙의 1건 충족·2건 위반, 보관 규칙의 3건 대기를 직접 비교할 수 있다.

지원하지 않는 전체 알고리즘 포트폴리오는 후속 단계이며, 이를 빈 성공 결과로 채우지 않는다.
대용량 성능·실제 정확도 개선 폭·모든 외부 OCEL producer와의 호환성은 알 수 없음이다.
이 설명의 유효범위는 2026-09-10의 PIX 0.4.0 구현과 기록된 시험이다. 구현·의미 정의가
변경되거나 독립 반례가 명시한 계약과 충돌하면 해당 지원·정확성 판단을 재검토한다.
