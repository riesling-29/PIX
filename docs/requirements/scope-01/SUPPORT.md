# SCOPE-01 세부 대체표 — 공통 입력·정렬·교환 편의 기능

기준일: **2026-09-14**. [전체 범례·증거·판정 경계](../2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md).
입력·출력은 대체할 기능을 검토하기 위한 계약이다. **현재 PIX가 이미 그 결과를 반환한다는 뜻은 아니다.** 현재 지원은 각 행의 구현·의미·소스·증거로 구분한다.
참조 경로와 symbol은 공식 배포 wheel의 위치다. wrapper·helper·backend는 추적을 위해 함께 표시하며 별도 계산 알고리즘으로 중복 집계하지 않는다.

| ID | 도메인에서 판단할 질문 | PIX 구현 | 의미 대응 | 다음 작업 |
|---|---|---|---|---|
| [PM-UTIL-001](#pm-util-001) | 사용자가 지정한 조건으로 case·event를 고르고 원본 근거를 유지할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [PM-UTIL-002](#pm-util-002) | 활동 순서와 case 순서를 사용자가 지정한 키로 바꾸되 가정을 기록할 수 있는가? | 대응 구현 없음 | 미구현 | IO-02, FILTER-03 |
| [PM-UTIL-003](#pm-util-003) | 기존 표의 case·활동·시각 열을 분석 입력으로 명시적으로 연결할 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-02, IO-03 |
| [PM-UTIL-004](#pm-util-004) | 어떤 열을 case·활동·시각으로 쓸지 계산 호출에 전달할 수 있는가? | 부분 대응 | PIX 자체 정의 | SCOPE-03 |
| [PM-UTIL-005](#pm-util-005) | 복합 classifier를 적용해 활동의 정체성을 정할 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-02 |
| [PM-UTIL-006](#pm-util-006) | case별 특정 이벤트 속성 값을 순서대로 읽을 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-02, STAT-01 |
| [PM-UTIL-007](#pm-util-007) | case 또는 event를 재현 가능한 표본으로 뽑을 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [PM-UTIL-008](#pm-util-008) | 간단한 활동 문자열로 검산용 로그를 만들 수 있는가? | 대응 구현 없음 | 미구현 | IO-02, QA-01 |
| [PM-UTIL-009](#pm-util-009) | 텍스트로 표현한 process tree를 모델로 읽을 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-02, MODEL-03 |
| [PM-UTIL-010](#pm-util-010) | 텍스트로 표현한 부분순서 모델을 읽을 수 있는가? | 대응 구현 없음 | 미구현 | MODEL-04, MODEL-03 |
| [PM-UTIL-011](#pm-util-011) | 로그와 모델을 메모리 내 바이트로 주고받을 수 있는가? | 부분 대응 | PIX 자체 정의 | IO-04, MODEL-03 |

## PM-UTIL-001

**사용자가 지정한 조건으로 case·event를 고르고 원본 근거를 유지할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | EventLog·EventStream·Trace와 사용자 predicate. |
| 확인할 출력 | 조건을 만족하는 case 또는 event로 구성한 로그·trace. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 일반 predicate 필터의 보존 정보·예외·빈 결과 계약을 구현한다. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | Python filter를 감싼 편의 진입점이다. 개별 도메인 필터 알고리즘과 중복 집계하지 않는다. upstream은 부적합 타입에서 원본을 반환하는 경로가 있다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/hof.py :: filter_log`
- `pm4py/hof.py :: filter_trace`

## PM-UTIL-002

**활동 순서와 case 순서를 사용자가 지정한 키로 바꾸되 가정을 기록할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·trace, 정렬 키 함수와 역순 옵션. |
| 확인할 출력 | case 또는 event의 순서를 재정렬한 로그·trace. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 원본 순서와 분석용 정렬 순서를 분리하고 동률·재현성을 기록한다. |
| 다음 작업 ID | IO-02, FILTER-03 |
| 의미·옵션·한계 | 일반 sort wrapper이다. PIX의 source-order 보존 또는 timestamp tie policy가 임의 정렬 API를 대신하지는 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/hof.py :: sort_log`
- `pm4py/hof.py :: sort_trace`

## PM-UTIL-003

**기존 표의 case·활동·시각 열을 분석 입력으로 명시적으로 연결할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | DataFrame·EventLog·EventStream와 case/activity/start/completion 열·날짜 형식. |
| 확인할 출력 | 열명·시각 타입·정렬·분석 property가 정리된 참조 로그 표현. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | PIX table mapping과 참조의 drop/정렬/시각 변환 정책을 대조하고 인메모리 rebase 범위를 정의한다. |
| 다음 작업 ID | IO-02, IO-03 |
| 의미·옵션·한계 | PIX의 명시적 CaseTableMapping·OCELTableMapping 기반 import는 존재한다. pandas/Polars 객체 API 호환까지 구현한 것은 아니다. |

**현재 PIX 근거:** `CaseTableMapping`, `OCELTableMapping`, `import_log`.
소스: [src/pix/tabular/mapping.py](../../../src/pix/tabular/mapping.py), [src/pix/io.py](../../../src/pix/io.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: format_dataframe`
- `pm4py/utils.py :: rebase`

## PM-UTIL-004

**어떤 열을 case·활동·시각으로 쓸지 계산 호출에 전달할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그 객체 및 분석 열명·추가 옵션, 또는 입력 타입. |
| 확인할 출력 | 분석 parameter dictionary 또는 Polars LazyFrame 여부. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PIX의 명시적 spec과 adapter 타입 처리로 대응할 범위를 기록한다. |
| 다음 작업 ID | SCOPE-03 |
| 의미·옵션·한계 | 참조의 parameter·backend 편의 helper이다. 같은 함수명이나 pandas/Polars 런타임 의존성을 PIX에 강제하지 않는다. |

**현재 PIX 근거:** `CaseTraceSpec`, `TraceSpec`.
소스: [src/pix/contracts/case_log.py](../../../src/pix/contracts/case_log.py), [src/pix/contracts/analysis.py](../../../src/pix/contracts/analysis.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: get_properties`
- `pm4py/utils.py :: is_polars_lazyframe`

## PM-UTIL-005

**복합 classifier를 적용해 활동의 정체성을 정할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그와 classifier 이름 또는 속성 목록. |
| 확인할 출력 | 복합 활동 값을 추가하고 activity property를 바꾼 참조 로그. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | classifier의 tuple 경계·결측·이름 충돌과 참조의 + 문자열 연결 의미를 구별한다. |
| 다음 작업 ID | IO-02 |
| 의미·옵션·한계 | PIX는 XES classifier를 보존하고 CaseTraceSpec.classifier로 trace를 투영한다. 원본 로그를 변경하는 set_classifier와 동일 API는 아니다. |

**현재 PIX 근거:** `CaseTraceSpec`, `case_traces`.
소스: [src/pix/contracts/case_log.py](../../../src/pix/contracts/case_log.py), [src/pix/event_log/adapters.py](../../../src/pix/event_log/adapters.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: set_classifier`

## PM-UTIL-006

**case별 특정 이벤트 속성 값을 순서대로 읽을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그와 case 식별 열 및 투영할 event 속성. |
| 확인할 출력 | case마다 선택 속성 값의 순서열. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 임의 속성·결측값의 투영 계약과 DataFrame별 순서 차이를 대조한다. |
| 다음 작업 ID | IO-02, STAT-01 |
| 의미·옵션·한계 | PIX case_traces는 활동·classifier 투영과 source order를 제공한다. 참조의 임의 속성 목록 및 Polars 정렬 분기는 별도 의미다. |

**현재 PIX 근거:** `case_traces`.
소스: [src/pix/event_log/adapters.py](../../../src/pix/event_log/adapters.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: project_on_event_attribute`

## PM-UTIL-007

**case 또는 event를 재현 가능한 표본으로 뽑을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 로그·OCEL, 표본 단위와 크기. |
| 확인할 출력 | 선택한 case 또는 event와 그에 따른 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | seed·중복·원본 ID·OCEL 관계 폐쇄·부분 trace를 명시한 표본 API를 구현한다. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | 참조는 입력 타입에 따라 표본 단위가 달라지는 경로가 있다. PIX 테스트의 한정 표본 사용을 제품 sampling API로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: sample_cases`
- `pm4py/utils.py :: sample_events`

## PM-UTIL-008

**간단한 활동 문자열로 검산용 로그를 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 구분자로 나눈 활동 문자열들의 집합. |
| 확인할 출력 | case ID와 합성 timestamp를 붙인 EventLog 또는 DataFrame. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 검산용 fixture 생성 편의는 검토하되 합성 시각을 실제 관측값과 구분한다. |
| 다음 작업 ID | IO-02, QA-01 |
| 의미·옵션·한계 | 참조는 임의 epoch부터 초 단위 timestamp를 만든다. PIX의 시간 결측 정책을 바꿀 근거로 쓰지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: parse_event_log_string`

## PM-UTIL-009

**텍스트로 표현한 process tree를 모델로 읽을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동과 sequence/XOR/parallel/loop/OR 연산자 문자열. |
| 확인할 출력 | ProcessTree 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 텍스트 문법과 지원 연산자를 정의하고 잘못된 식의 오류를 검증한다. |
| 다음 작업 ID | MODEL-02, MODEL-03 |
| 의미·옵션·한계 | PIX ProcessTree 자료형 및 자체 model JSON과 별개인 교환 문법이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: parse_process_tree`

## PM-UTIL-010

**텍스트로 표현한 부분순서 모델을 읽을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | POWL 모델의 문자열 표현. |
| 확인할 출력 | POWL 모델. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | POWL 모델 의미와 문법을 도입할 때 함께 구현한다. |
| 다음 작업 ID | MODEL-04, MODEL-03 |
| 의미·옵션·한계 | 추가 주석 없음. 남은 개발·검증 조건을 따른다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: parse_powl_model_string`

## PM-UTIL-011

**로그와 모델을 메모리 내 바이트로 주고받을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | EventLog·DataFrame·PN+markings·process tree·BPMN·DFG 또는 타입 태그와 bytes. |
| 확인할 출력 | XES·Parquet·PNML·PTML·BPMN·DFG bytes와 타입 태그, 또는 복원한 참조 객체. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 참조의 형식별 memory I/O를 해당 writer/reader 작업에 연결한다. |
| 다음 작업 ID | IO-04, MODEL-03 |
| 의미·옵션·한계 | 기존 format dispatch wrapper이다. PIX 자체 model/result JSON 교환은 구현돼 있으나 이 6종 직렬화 형식 호환을 뜻하지 않는다. |

**현재 PIX 근거:** `model_json_bytes`, `model_from_json`, `result_json_bytes`, `result_from_json`.
소스: [src/pix/models.py](../../../src/pix/models.py), [src/pix/results.py](../../../src/pix/results.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/utils.py :: serialize`
- `pm4py/utils.py :: deserialize`
