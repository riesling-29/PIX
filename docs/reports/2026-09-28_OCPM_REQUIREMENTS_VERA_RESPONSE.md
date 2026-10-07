# OCPM 추가 개발 요구사항에 대한 Vera 답변

작성일: 2026-09-28 (Asia/Seoul). 성격: 코드 근거에 따른 요구사항 검토와 계획 결정. 구현 완료 보고가 아니다.

## 1. 검토 기준과 권한

- PIX 코드: `8a669844e4781757a22f8caa0ff45f3ad6a30943`, `feat/ocel-readers-v0.2.0`, package 0.5.0.
- 검토 문서: Provenance의 [OCPM 추가 개발 요구사항](https://github.com/riesling-29/PIX/blob/d8b36c86e54f626720adc335f064925ae6686e1f/docs/requirements/OCPM_추가개발_요구사항.md), Gesso의 동 커밋 VIS UX 리뷰·확정 카피.
- 문서 브랜치: `cursor/ocpm-requirements-docs-485e`, tip `d8b36c86e54f626720adc335f064925ae6686e1f`.
- 이전 charter: `e1796ece1326558a893b2f7562db5ab6da9df36c`의 [Appendix A·DS 포함 전문](https://github.com/riesling-29/PIX/blob/e1796ece1326558a893b2f7562db5ab6da9df36c/docs/audits/ALGORITHM_COMPLETENESS_REVIEW_CHARTER.md).
- 사용자는 이번 답변서·계획 변경의 작성과 commit을 요청했다. 개별 계산 의미에 대한 사용자 도메인 승인을 대신 기록하거나, Ashlar와의 새 합의를 주장하지 않는다.
- 이번에는 제품 코드, runtime schema, registry 등급, 사용자 177개 선택, ILP 공동 설계 전 보류 조건을 바꾸지 않는다. 구현은 후속 작업이다.

## 2. 동의하는 방향

관측적 OCPN의 한계, joint/object replay/flattened의 구별, 투영의 원본 대응, 집계 정의와 미확정 값, qualifier·객체 이력의 실제 사용 범위를 화면까지 전달해야 한다. Graphviz·Chevron·기존 결과 계약을 재사용하고, 단순 표시 개선을 새 계산 알고리즘으로 포장하지 않는다.

수집·Agent 실행·운영 정책은 소비자, 계산은 PIX라는 경계를 유지한다. 코드 정확성과 도메인 의미 승인은 별도다. 미구현, 구현됐으나 비교 미검증, 소비자에서 아직 미허용인 상태도 서로 다르다.

## 3. 원문 ID별 결정

아래의 수용은 개발계획 반영 결정이다. 모든 항목이 새 구현이 필요하다거나 이미 완료되었다는 뜻이 아니다. P0는 이 추가 계약 작업의 선행 순서이며 재현된 치명적 결함 등급이 아니다.

| 원문 ID | 결정 | 반영 방식·수정 조건 |
| --- | --- | --- |
| P0-01 | 수용, 기존 계약 우선 | `compute/ocpn_discovery.py`의 `observational_cardinality_bounds`, `joint_soundness_not_established`를 우선 재사용. 성공 payload가 없는 실패 결과까지 새 필드를 강제하지 않고 해당 상태·원인과 연결한다. |
| P0-02 | 수정 수용 | 연산자 identity는 구분한다. 수치가 반드시 다르다는 일반 명제는 채택하지 않는다. 차이가 생기는 공유 이벤트 반례와 수치가 같아도 의미가 다른 정상 사례를 함께 검증한다. |
| P0-03 | 수정 수용 | event pair/object/occurrence는 원시 count의 집계 단위다. 비율의 분모와 구분한다. 기존 필드와 계산 정의를 먼저 문서화하고 표시 선택 metadata가 부족할 때만 확장한다. |
| P0-04 | 수정 수용 | projection v2의 기존 `describe()`와 shared-event group 함수를 재사용한다. receipt 요약·시각화 연결을 추가 대상으로 삼되, 원본 identity나 기존 projection profile을 이유 없이 변경하지 않는다. |
| P0-05 | 수용 | qualifier·객체 이력 사용표를 작성한다. 사용/필터 선택/보존만 함/계산에 미사용을 구분한다. 전 연산 개조나 일괄 경고는 하지 않는다. |
| P0-A1 | 수정 수용 | sequence·n-gram·일반 sequential pattern·OC 부분순서를 구분한다. 기존 contextual n-gram을 먼저 연결하며 신규 패턴 엔진 착수로 해석하지 않는다. |
| VIS-P0-01…07 | 수정 수용 | 뷰·집계·관측성·상태·투영·단위·layout 실패 표시를 기존 viewer에 연결한다. 아래 카피 정정을 선행한다. |
| P1-01 | 수용 | object context의 모집단·분모·종료 의미를 기존 profile과 연결한다. |
| P1-02 | 조건부 수용 | OPERA annotation과 요약 통계를 구분. 실제 부족한 필드·통계가 확인된 범위만 설계한다. |
| P1-03 | 조건부 수용 | silent/flooding 정책의 기존 구현을 먼저 확인하고 부족한 계약만 추가한다. |
| P1-04 | 수정 수용 | exact variant 동치·예산 계약과 테스트가 이미 있다. 신규 동형성 알고리즘이 아니라 기존 보장과 잔여 범위의 추적부터 수행한다. |
| P1-05…08 | 조건부 수용 | filter·graph comparison·모델 변환·enrichment별 기존 함수와 독립 반례를 대조한 후 실제 잔여분을 확정한다. registry partial만으로 미구현을 선언하지 않는다. |
| P1-09 | 조건부 수용 | pre4와 변경된 표준 판본을 고정해 차이를 조사한다. 이번에는 외부 표준 최신 상태를 검증하지 않았으며 최종본 존재·준수를 주장하지 않는다. |
| P1-10 / VIS-P1-01…07 | 수용, 의미 정정 선행 | 기존 visualization 확장. 접근성·밀도·손실 표시를 검증하고 view filter와 분석 모집단 변경을 구분한다. |
| P1-11 | 수정 수용 | 기존 n-gram부터 선형화 반례를 작성. 이를 일반 sequential mining 지원이나 OC 모델 발견으로 부르지 않는다. |
| P1-12 | 수용 | 입력 규모·탐색 예산·종료 이유·payload/evidence 범위를 표로 작성. 복잡도 상한과 실제 성능 측정을 구분한다. |
| P1-13 | 수정 수용 | canonical OCEL collection 순열과 source-order CaseLog를 구분. object-type 제거에 보편적 단조성을 가정하지 않는다. 근사 비용 경계와 통계적 CI도 분리한다. |
| P2-01…05 | 보류 백로그 유지 | 기존 장기 대체 목표를 축소하지 않지만 이번 계획으로 신규 기능·stream·lineage·대체 검증 캠페인 전체에 착수하지 않는다. |

표의 원문 ID는 `OCPM-` 접두사를 생략했다. 조건부 항목은 공백 조사만 계획에 넣으며 의미가 미정인 새 알고리즘을 자동 승인하지 않는다.

## 4. 계산·카피 정정 요청과 근거

### 집계 단위는 비율의 분모가 아니다

`src/pix/compute/ocdfg.py::discover_ocdfg`는 edge별로 다음 값을 동시에 계산한다.

- `event_pair_count`: 서로 다른 `(source_event_id, target_event_id)` 수.
- `unique_object_count`: 그 edge에 참여한 서로 다른 객체 수.
- `occurrence_count`: 객체별 직접후행 이벤트 쌍의 발생 수.

동일 객체가 A→B를 반복하면 occurrence는 늘지만 고유 객체 수는 늘지 않는다. 여러 객체가 같은 이벤트 쌍을 공유하면 occurrence는 늘어도 event pair 수는 늘지 않을 수 있다. 복수 qualifier는 해당 객체의 발생 수를 늘리지 않는다.

근거 테스트: `tests/compute/test_ocdfg.py::test_shared_and_repeated_pairs_distinguish_all_three_count_units`, `test_qualifier_view_preserves_excluded_objects_but_does_not_create_o2o_edges`.

Gesso의 `(사건, 객체[, qualifier])` 문구는 OCDFG edge에 그대로 적용할 수 없다. 노드/edge별 집계 정의를 나누고, 비율을 실제 제공하는 경우에만 분자·분모·분모 0 정책을 추가한다. `denominator_profile_id`라는 새 이름을 기존 raw count 전체에 강제하지 않는다.

### 서로 다른 연산이 항상 서로 다른 숫자를 내는 것은 아니다

joint와 flattened의 의미·operator identity는 다르다. 그러나 둘 다 완전히 적합한 단순 로그에서는 수치가 같을 수 있다. 부등 assertion만 만족하는 fixture는 정확성 oracle이 아니다. 입력 참여관계, 모델, move cost, 집계 모집단을 고정하고 손계산 또는 독립 탐색으로 각 기대값을 만든다. 올바른 차이량을 산정하지 못하면 그 수치 검증은 미완료로 남긴다.

### 기존 구현을 신규 개발로 중복 산정하지 않는다

- `object_centric/case_projection.py::ObjectCaseProjection.describe`: source/derived digest, spec, occurrence 원본 대응, 제외 이벤트, 동률 객체, O2O·이력 경계를 제공한다. `shared_event_case_groups`, `audit_projected_split`도 존재한다. 새 표시는 group 수·정의와 함께 연결하고 모든 자원 공유를 누출로 보지 않는다.
- `tests/compute/test_variants.py`: exact 동치와 `test_symmetric_search_limit_returns_no_partial_exact_groups` 등 예산 실패 테스트가 존재한다.
- `case_centric/context_ngrams.py`: recorded-order CaseLog 기반 n-gram 집계가 있다. OC 입력에는 명시적 투영·선형화가 필요하다. 이것이 일반 frequent episode/subsequence 알고리즘 전체를 의미하지는 않는다.
- `case_centric/conformance_approximation.py`: 비용 상·하한과 witness를 제공한다. 통계적 신뢰구간과 달리 독립 최적 비용의 구간 포함을 먼저 검증한다. seed·subset 크기에 따른 구간 폭·계산량은 별도 품질 실험이다.

### 화면이 새 의미를 만들지 않도록 한다

`partial`을 항상 “집계 일부만 계산”으로 풀지 않는다. evidence만 생략된 경우, 모집단 일부가 제외된 경우, 계산 자체가 미완료인 경우를 결과 issue와 coverage에 따라 구분한다. `invalid_input`을 layout error로 숨기지 않는다.

투영 배너의 “OC 원본 진실이 아닙니다”는 “선택한 객체형·순서 정책으로 투영한 Case 분석이며 원본의 모든 관계를 표현하지 않습니다”로 바꾼다. receipt 부재는 출처·손실 확인 불가이지, 모든 Case KPI가 수학적으로 무효라는 판정은 아니다. 엄격한 소비자가 이를 차단할지는 명시적 소비자 정책이다.

관측적 배지는 해당 discovery provenance에 붙인다. 외부에서 읽은 모든 OCPN까지 PIX 관측적 discovery 산물로 표시하지 않는다. soundness 미입증과 반증도 구분한다. 같은 source digest만으로 모집단·profile·model이 같은 분석이라고 연결하지 않는다.

## 5. 문서 연결 및 협업

새 요구 브랜치는 코드 `8a66984`에서 분기했다. 그 안의 charter는 8줄 workspace 포인터이며, 기존 charter 브랜치의 236줄 전문과 같은 경로를 사용한다. 기존 원격 전문을 삭제한 것은 아니지만 두 브랜치 통합 시 조정이 필요하다. 전문을 보존하거나 위 고정 GitHub 링크를 사용해야 한다. `/workspace/...`는 저장소 독자가 접근할 수 있는 근거가 아니다.

`PI_FOLLOWUP_SECTION_FOR_CHARTER.md`는 확인한 PIX·Schumpeter 원격 브랜치에서 찾지 못했다. 해당 답변서가 따로 존재하면 판본을 받아 연결해야 하며, 그 내용을 검토했다고 주장하지 않는다.

후속 코드 변경 PR 전 작업 브랜치·경로·공유 계약을 사용자/개발팀에 공유할 준비를 한다. 이번에는 코드 PR, 타 저장소 변경, 개발팀 메시지 전송을 하지 않는다. 현재 문서는 Vera의 응답이며 개발팀의 재승인 기록이 아니다.

## 6. 검증 범위·철회 조건

이번 9월 28일 작업은 문서와 코드의 읽기 대조 및 문서 변경 검사다. 제품 테스트는 재실행하지 않았다. 9월 26일 집중 실행의 757 passed, 1 skipped, 48 subtests 및 Schumpeter self-test 통과는 과거 별도 실행이며 이번 계획의 미구현 항목 통과 증거로 사용하지 않는다. 전체 대체율·실무 성공률·신규 작업 공수·대규모 성능은 알 수 없음이다.

위 SHA·profile에 한해 판단이 유효하다. 다른 profile 정의, 기존 테스트의 반례 미검증, 계산/codec 변경, 새 표준 판본, 독립 반례가 확인되면 해당 결정과 수락 사례를 재검토한다. 기존 구현으로 충분한 항목은 코드 무변경과 문서·테스트 연결만으로 처리할 수 있다.

## 7. 결정

표시까지 이어지는 OCPM 의미 계약 강화는 계획에 반영한다. 집계 단위·연산별 기대값·기존 구현 재사용을 선행하고, 수정한 수락 기준으로 [개발계획 변경안](../requirements/2026-09-28_OCPM_DEVELOPMENT_PLAN_AMENDMENT.md)을 적용한다.
