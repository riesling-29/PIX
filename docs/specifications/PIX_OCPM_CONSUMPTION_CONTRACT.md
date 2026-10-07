# OCPM 소비 계약과 지원 근거

작성일 2026-09-28. 기준 코드 `8a66984` (계획 commit `2b515bc`). OC-PATCH-01의 1차 조사다. 구현 존재와 실제 실행·참조 대체 검증은 구별한다. 아래에서 '미확인'은 미구현이라는 뜻이 아니다.

후속 상태 (2026-10-04): 아래 표는 최초 조사 snapshot이다. `4e0b471`에서 downstream projection의 명시적 `projection=` 연결과 입력별 `issues_json`, panel별 해석 표시를 구현·검증했다. 해당 행의 '추가 설계 필요'는 최초 상태를 뜻한다. 전체 입력 사용표와 P1 조사 완료는 아니다. 현재 실행 근거는 [원격 인계서](../reports/2026-10-04_PIX_GITHUB_VALIDATION_HANDOFF.md), 잔여 작업은 [후속 계획](../requirements/2026-10-04_PIX_PARALLEL_DEVELOPMENT_PLAN.md)을 따른다.

## 확인한 계약과 잔여 작업

2026-10-06 1차 확장: [공개 입력 의미 감사](../reports/2026-10-06_PIX_OCPM_INPUT_AUDIT.md)에
명시한 namespace의 170개 정의와 20개 함수의 입력 사용표를 연결했다.
ETOT/OTG edge 비교와 OCCN 양방향 변환·loss/refusal의 기존 경로를 확인했다.
아래 최초 표의 '미확인'은 해당 범위에서 갱신되지만, 전 함수 감사나 참조 대체 검증 완료는 아니다.

| 요구 | 기존 owner·계약 | 근거 테스트 | 이번 판단 / 잔여 |
| --- | --- | --- | --- |
| P0-01 | `compute/ocpn_discovery.py`, `viewer/visual_model_results.py::_ocpn_discovery`: cardinality/fitting 보장과 issues, 요약 패널 | `tests/compute/test_ocpn_discovery.py`, `tests/viewer/test_visual_model_results.py` | 관측성 계약·표시 일부 존재. 모든 상태에서 상시 표시되는지는 browser 확인 필요 |
| P0-02 | `compute/object_conformance.py` alignment, `object_centric/conformance.py` joint token/flattened replay; viewer `_alignment/_replay/_flattened` | `tests/object_centric/test_conformance.py` | 이미 다른 연산. 아래 사례는 replay 비교이며 alignment 전체 oracle이 아님 |
| P0-03 | `compute/ocdfg.py`, viewer `_ocdfg`: event pair/object/occurrence와 evidence 일치 검사 | `tests/compute/test_ocdfg.py`, `tests/viewer/test_visual_object_adapters.py` | 세 집계가 이미 별도 저장됨. 신규 분모 계산 불필요. 표시 선택·범례는 후속 UI 검증 |
| P0-04 | projection v2 `describe`, `shared_event_case_groups`, `audit_projected_split` | `tests/object_centric/test_case_projection.py`, `tests/test_review_boundaries.py` | 원본/파생 identity 존재. downstream 결과와 receipt의 명시 연결은 추가 설계 필요 |
| P0-05 | 각 연산 spec의 qualifier 선택, projection 원본 이력 보존 | 위 tests 및 `tests/object_centric/test_enrichment.py` | 전 연산 사용표는 조사 중. '보존'을 'as-of 계산 사용'으로 부르지 않음 |
| P0-A1 / P1-11 | `case_centric/context_ngrams.py`: 명시적 CaseLog 순서 | `tests/case_centric/test_context_ngrams.py` | n-gram 존재. 일반 subsequence/episode mining은 이 근거로 지원 주장 안 함 |
| P1-01 | `compute/object_context.py` | `tests/compute/test_object_context.py`, `test_object_context_oracle.py` | binding-prefix 계약 재사용; 공개 설명과 종료 상태 대조 필요 |
| P1-02 | `object_centric/performance.py`, `model_integration.py::enhance_ocpn`, viewer `_performance/_replay_performance` | `tests/object_centric/test_performance.py` | annotation 자체를 미구현으로 볼 수 없음. 요구별 요약 통계 공백 조사 필요 |
| P1-03 | `object_centric/conformance.py::_closure`, `ObjectReplaySpec` | `tests/object_centric/test_conformance.py` | silent 한도와 미확정 사례 존재; 참조 flooding 정책 전체 동치는 미확인 |
| P1-04/12 | `compute/variants.py` exact labeling와 budget | `tests/compute/test_variants.py` | 동치·한도 계약 이미 존재. 대규모 성능은 미측정 |
| P1-05 | `object_centric` filtering 계열 | `test_advanced_filtering.py`, `test_filter_predicates.py` | frequency/cardinality/execution 등 의미 테스트 존재. time/lifecycle/perf 전 범위 대조 미완료 |
| P1-06 | `object_centric/graph_comparison.py` | `tests/object_centric/test_graph_comparison.py` | OCDFG 비교 존재. ETOT/OTG 대칭 profile 범위는 미확인 |
| P1-07 | `object_centric/models.py`, `model_integration.py` | 관련 model tests 조사 필요 | OCCN 양방향 변환 loss 요구에 대한 개별 보장 미확인 |
| P1-08 | `object_centric/enrichment.py` | `test_lifecycle_manual_boundaries_singleton_both_and_selected_source_qualifiers`, `test_lifecycle_existing_roles_never_overwrite_and_can_skip_identical` | first/last·충돌 관련 구현/테스트 존재. 전면 신규 개발 불필요 |
| P1-09 | pre4 import profile | 기존 OCEL reader tests | 최신 표준 조회·판본 diff 미실행 |
| P1-10 / VIS | `viewer/visual_contracts.py`, adapters, `assets/visualization.js` | `tests/viewer/` | provenance는 panel/input별 연결, SVG metadata 포함. 화면 수락 전체는 미확인 |
| P1-13 | OCEL canonical 정규화, recorded-order CaseLog, 근사 비용 경계 | 기존 permutation·approximation tests | 하나의 일괄 순열/통계 CI 규칙으로 대체하지 않음 |

## 계산 입력 사용표 — 확인한 최소 범위

| 경로 | Qualifier | 객체 속성 이력 | 해석 |
| --- | --- | --- | --- |
| OCDFG | spec 선택과 evidence; 복수 역할이 occurrence를 곱하지 않음 | 직접후행 count에 사용하지 않음 | 시간 순서는 event timestamp와 tie 정책 |
| object replay/flattened | 명시 선택 후 참여 객체 중복 제거 | 해당 token 계산의 as-of feature가 아님 | 모델 token·binding 제약과 event 순서 |
| object→case projection | 원본 event participation 대응 보존 | full history 보존 | observation cutoff-safe feature라는 보장은 아님 |
| lifecycle enrichment | source role 선택, 출력 qualifier와 충돌 정책 | boundary는 event 참여 시점 | 객체 속성 변경을 자동 lifecycle event로 만들지 않음 |
| contextual n-gram | CaseLog에 어떤 값을 넣을지는 명시적 입력/profile에 따름 | OCEL 이력을 자동 소비하지 않음 | 선형 trace의 token window |

이 표는 전체 공개 연산 inventory가 아니다. constraints/filtering/features의 속성 사용은 각 profile을 추가 조사해야 한다. 원본에 값을 보존했다는 이유만으로 계산에 사용했다고 표시하지 않는다.

## 저장·표시 경계에서 확인한 공백

`VisualizationDocument`는 기존 `VisualField`, `VisualMetric`, panel별 `VisualProvenance`를 제공하므로 새 envelope가 필요하지 않다. `build_visualization`은 계산 issue의 code/message를 문서 공통 문자열로 보존하지만, 계산별 provenance에는 구조화한 issue 위치(`at`)가 없었다. 여러 입력을 섞으면 어떤 원인·위치가 어느 계산에 속하는지 상세하게 복원할 수 없다. 이 공백은 기존 provenance details의 선택적 JSON 필드로 보완할 수 있으며 계산/codec schema 변경이 필요하지 않다.

## 유효성과 미완료

기준 코드의 읽기 대조이며 실행 결과는 별도 작업 보고서에 남긴다. 참조 대체 검증 상태나 사용자 도메인 승인 상태는 바꾸지 않는다. 코드/profile/표준 변경 또는 독립 반례가 나오면 관련 행을 재검토한다. 기존 지원이면 무변경이 유효한 완료 방식이다.
