# OCPM 세부 패치 계획

작성일: 2026-09-28. 최초 작성 시 상태는 패치 설계 / 구현·신규 테스트 미착수였다. 이후 일부 구현·검증을 진행했으며 현재 상태는 [진행 기록](../reports/2026-09-28_OCPM_PATCH_PROGRESS.md)을 따른다. 아래 항목은 전체 완료 선언이 아니다.

2026-10-04 기준점 이후의 작업 분할·파일 ownership·수락 조건은 [후속 세부 계획](2026-10-04_PIX_PARALLEL_DEVELOPMENT_PLAN.md)을 따른다. 기존 패치 번호와 요구 의미는 유지한다.

상위 결정: [개발계획 변경](2026-09-28_OCPM_DEVELOPMENT_PLAN_AMENDMENT.md), [Vera 답변서](../reports/2026-09-28_OCPM_REQUIREMENTS_VERA_RESPONSE.md).
저장소 기준: `2b515bcaa674f90cddf438fdfa4f6916e03e3d47`, `feat/ocel-readers-v0.2.0`; 제품 코드 기준은 동일 내용의 `8a66984`. 외부 요구 기준은 `d8b36c8`이다.

## 1. 작업 방식과 변경 경계

아래 패치는 검토·회귀·되돌리기가 가능한 변경 묶음이다. 파일은 현재 트리에서 확인한 변경 후보이며 모두 수정하라는 뜻은 아니다. 기존 동작이 수락 기준을 충족하면 문서·테스트 근거만 연결하고 제품 코드는 유지한다.

후속 구현 브랜치 제안은 `feat/ocpm-contracts-and-views`다. 아직 생성하지 않았다. 구현 시작 시 최신 코드와 미커밋 변경을 확인하고, 코드 PR 전에 브랜치·파일·공유 계약 변경을 개발팀과 조율할 정보를 제공한다. 이번 계획 작성으로 메시지 전송·코드 PR·타 저장소 수정을 수행하지 않는다.

Canonical V1, projection v2, 기존 operator identity, 계산 수식, 177개 사용자 선택, ILP 보류 조건을 유지한다. 표시를 정돈하려고 전역 version을 올리거나 새 범용 registry/envelope를 만들지 않는다. Schumpeter의 receipt 신선도 결함은 별도 저장소 작업이다.

## 2. 패치 순서와 의존성

| 패치 | 역할 | 선행 | 구현 범위 |
| --- | --- | --- | --- |
| OC-PATCH-01 | 함수·profile·테스트·공백 대조표 | 없음 | 문서 |
| OC-PATCH-02 | 도메인 사례와 독립 기대값 | 01 | 문서·테스트 |
| OC-PATCH-03 | 표시 의미·상태·직렬화 계약 | 01, 관련 02 | 최소 viewer 계약 |
| OC-PATCH-04 | OCDFG 집계와 연산자 표시 | 03, 관련 02 | adapter |
| OC-PATCH-05 | projection receipt 소비 경로 | 03, 관련 02 | projection/viewer 경계 |
| OC-PATCH-06 | OCPN 관측성·미확정 표시 | 03 | adapter·provenance |
| OC-PATCH-07 | 실제 화면·export·접근성 | 04…06 | 기존 JS/CSS·export |
| OC-PATCH-08 | 한도·sequence·근사 품질 | 01, 관련 02 | 문서·테스트·실험 |
| OC-PATCH-09 | 조건부 P1의 잔여 작업 확정 | 01, 관련 08 | 조사·후속 설계 |
| OC-PATCH-10 | 통합 검증·인계 | 이번 구현 범위의 패치 완료 | 검증·보고 |

08의 기존 한도 조사와 09의 지원 대조는 viewer 작업과 독립적으로 진행할 수 있다. 새로운 의미가 미정인 항목만 보류하고 나머지를 진행한다. 01·02에서 불필요하다고 판명된 제품 패치는 생략한다.

## 3. 패치별 설계

### OC-PATCH-01 — 지원·공백·사용 의미 대조표

- 연결: OC-PLAN-01, OCPM-P0-01…05, P1-01…09/12.
- 조사 owner: `compute/ocdfg.py`, `compute/ocpn_discovery.py`, `compute/variants.py`, `compute/object_context.py`, `object_centric/{conformance,case_projection,performance,filtering,enrichment}.py`와 관련 공개 진입점.
- 문서 산출물 제안: `docs/specifications/PIX_OCPM_CONSUMPTION_CONTRACT.md`. 각 요구에 함수, profile, 결과 필드, 기존 테스트, 실행 여부, 잔여 공백을 연결한다. qualifier·이력은 계산 사용/선택 조건/보존만 함/미사용으로 나눈다.
- 구현 존재, PIX profile 검증, 참조 대체 검증, Skill 허용을 별도 열로 기록한다. registry 상태는 이 조사만으로 승격하지 않는다.
- 종료 기준: 모든 원문 P0/P1 ID의 근거 또는 미확인 이유가 있고 코드 변경 대상이 실제 공백으로 한정된다. 신규 테스트가 없어도 충분하면 무변경으로 종료한다.

### OC-PATCH-02 — 사용자가 판단할 작은 로그와 독립 기대값

- 연결: OC-PLAN-02, P0-02/03/A1, P1-01/11/13.
- 산출물 제안: `docs/user-guide/OCPM_DOMAIN_REVIEW_CASES.md`; 필요한 경우 기존 tests fixture에 최소 사례 추가. 사용자 승인란은 미검토로 둔다.
- count 사례: 객체 x의 trace가 e1:A→e2:B→e3:A→e4:B, 객체 y가 e1:A→e2:B라면 A→B의 event pair=2, unique object=2, occurrence=3이다. y의 참여 qualifier를 추가해도 이 세 값은 같다. 비율을 만들지 않았으므로 분모 필드는 필요하지 않다.
- conformance 사례: shared-event 제약을 위반하는 로그와 모든 경로가 적합한 단순 로그를 각각 사용한다. 모델·비용·모집단을 고정한 후 독립 token 추적/유한 탐색으로 기대값을 구한다. 비교 지표의 척도가 다르면 먼저 정의를 설명하며 숫자 부등만을 oracle로 삼지 않는다.
- projection 사례: 원본 event가 두 case에 나타나는 것과 Agent/Resource만 공유하는 독립 Task를 분리한다. n-gram 사례는 입력 선형화 정책과 단위를 명시한다. n-gram 결과를 OC 모델이나 일반 sequential pattern 지원으로 해석하지 않는다.
- 테스트 owner: `tests/compute/test_ocdfg.py`, `tests/object_centric/test_conformance.py`, `tests/compute/test_object_conformance_oracle.py`는 존재 여부·적용 범위를 확인 후 사용, `tests/test_review_boundaries.py`, `tests/object_centric/test_case_projection.py`, `tests/case_centric/test_context_ngrams.py`.
- 종료 기준: 사건·참여관계 표만으로 기대값을 검산할 수 있고, golden 생성에 production 계산 함수를 재사용하지 않는다. 검산 불가능한 기대값은 미확정으로 남긴다.

### OC-PATCH-03 — 기존 viewer 의미 계약과 codec

- 연결: OC-PLAN-03, VIS-P0-01/02/03/06.
- owner: `viewer/visual_contracts.py`의 `VisualField`, `VisualMetric`, `VisualProvenance`, `VisualizationDocument`; `visual_serialization.py::{_decode,visual_from_dict,visual_to_dict}`; `visualization.py::{_source_metadata,build_visualization}`.
- 우선 기존 field/metric/provenance로 view 종류, 선택 집계, operator, 계산 상태·issue·coverage를 전달한다. 구조화 필드가 정말 필요할 때만 해당 owner에 추가한다. proposed key는 명세에서 확정하며 Gesso의 이름을 검증 없이 runtime schema로 이식하지 않는다.
- 상태 mapping: computed/partial/unavailable/invalid_input을 유지하고, 계산 미완료·집계 제외·evidence 생략·렌더링 오류를 별도 원인으로 보여 준다. 모든 partial을 '일부 집계 누락'이라고 설명하지 않는다.
- 호환성 반례: 기존 저장 문서 읽기, unknown field/schema 진단, 잘못된 enum, null metric 보존, 같은 source의 서로 다른 operator/spec/model 구별. 새로운 codec 동작이 필요하면 해당 visualization version과 읽기 정책을 명세한다. 계산 result version은 자동 변경하지 않는다.
- 테스트: `tests/viewer/test_visual_contracts.py`, `test_visualization.py`, `tests/test_results.py`, `tests/test_extended_results.py` 중 실제 영향 범위.
- 종료 기준: 저장/복원 후 원래 의미가 같고 provenance 누락으로 성공이나 관측성 보장을 만들어내지 않는다.

### OC-PATCH-04 — OCDFG count와 conformance별 표시

- 연결: P0-02/03, VIS-P0-01/02/05/06.
- owner: `viewer/visual_object_adapters.py::{_ocdfg,_alignment,_replay,_flattened,object_panels}`; 필요 시 `visual_case_adapters.py`의 해당 case panel.
- OCDFG의 세 count는 계산 결과를 그대로 읽는다. edge occurrence는 객체별 직접후행 쌍의 발생으로 표시한다. 노드 발생·edge 발생·qualified relation 수를 혼합하지 않는다. normalized metric을 제공한다면 그 경우에만 분자·분모·0분모 정책을 보인다.
- joint/object replay/flattened는 operator identity와 서로 다른 해석을 표시한다. 같은 숫자라고 같은 연산으로 합치지 않고, 다른 단위의 fitness를 무조건 한 카드에 비교하지 않는다.
- 테스트: `tests/viewer/test_visual_object_adapters.py`, `test_visual_case_adapters.py`, `tests/compute/test_ocdfg.py`, `tests/object_centric/test_conformance.py`. 02의 count 사례가 panel→JSON→export까지 그대로 이어져야 한다.
- 종료 기준: metric 선택과 라벨이 함께 변경되며 표시 변경이 source 계산값·computation ID를 바꾸지 않는다.

### OC-PATCH-05 — projection receipt와 파생 case 분석 연결

- 연결: P0-04, VIS-P0-04.
- owner: `object_centric/case_projection.py::{ObjectCaseProjection.describe,shared_event_case_groups,audit_projected_split}`, `viewer/visualization.py::build_visualization`, 관련 case/object adapter.
- receipt에 이미 있는 source/derived digest, spec, 원본 event 대응, 제외·동률 정보를 재사용한다. grouping은 단순 그룹 수뿐 아니라 그룹 기준과 단독 case 포함 여부를 명시한다. summary 필드 신설은 실제 필요 시에만 한다.
- 설계 결정 지점: downstream CaseLog 결과에서 receipt를 복원할 수 있다고 가정하지 않는다. 기존 source/provenance 인자로 전달 가능한지 조사하고, 불가능하면 backward-compatible 명시적 선택 인자를 제안한다. 임의 CaseLog에 OC lineage를 붙이지 않는다.
- 배너: '선택한 객체형·순서 정책으로 투영한 Case 분석이며 원본의 모든 관계를 표현하지 않습니다.' receipt 미제공은 출처 미확인, digest 불일치는 충돌로 구별한다. 엄격한 소비자의 KPI 승인 정책은 PIX 계산과 분리한다.
- 반례: 다른 source의 receipt, 다른 derived digest, shared event 없는 case, 같은 자원만 공유, 여러 qualifier, 빈 객체, receipt 없는 기존 호출, 너무 큰 원본 ID 목록의 요약과 상세 evidence 구별.
- 테스트: `tests/object_centric/test_case_projection.py`, `test_review_identity.py`, `tests/test_review_boundaries.py`, `tests/viewer/test_visual_case_adapters.py`, `test_visualization.py`.
- 종료 기준: 기존 API 호출과 projection v2 identity는 유지하고, receipt 불일치를 조용히 수용하지 않는다. 계산용 분할 정책을 viewer가 자동 변경하지 않는다.

### OC-PATCH-06 — OCPN 관측성·coverage·한도 표시

- 연결: P0-01, VIS-P0-03/06.
- owner: `viewer/visual_model_results.py::_ocpn_discovery`, `visual_model_adapters.py`, `visualization.py::_source_metadata`. 계산 owner는 `compute/ocpn_discovery.py`와 기존 계약이며 실제 결함이 없으면 수정하지 않는다.
- 기존 observational/soundness issues와 discovery 결과를 연결한다. raw/imported OCPN은 discovery provenance가 없다고 표시하며 자동 관측적 배지를 부여하지 않는다. 'soundness 미입증'을 'unsound'와 구별한다.
- 반례: 정상 witness, state bound, failed parent, locally sound이지만 joint deadlock인 모델, evidence 생략만 있는 결과, payload 없는 invalid input. 실패한 parent 근거로 성공 panel을 승인하지 않는다.
- 테스트: `tests/compute/test_ocpn_discovery.py`, `tests/viewer/test_visual_model_results.py`, `test_visual_model_adapters.py`, `test_visual_annotations.py`.
- 종료 기준: 원본 계약의 보장 이상을 화면이 주장하지 않는다. 계산 완료와 evidence 표시량이 따로 설명된다.

### OC-PATCH-07 — 실제 UI·export·접근성

- 연결: OC-PLAN-04, VIS-P0 전체와 VIS-P1.
- owner: `viewer/assets/visualization.js`, `visualization.css`, 필요 시 `viewer/export.py` 및 기존 rendering 진입점. vendor·Graphviz 배치 알고리즘은 기본 변경 범위가 아니다.
- adapter metadata에 따른 뷰 정의·집계 단위·operator·관측성·투영 배너·진단을 렌더링한다. 문자열을 HTML로 무검증 삽입하지 않는다. 긴 ID/한국어/작은 viewport에서도 문구가 잘리지 않도록 확인한다.
- 색 외 텍스트 표시, 키보드 선택·focus, 상세 진단 접근을 제공한다. 표시 edge 필터가 계산 모집단을 바꾼 것처럼 보이지 않게 한다. Chevron 가로·세로 모두 슬롯≠시간 도움말을 제공한다.
- JS/browser owner: `tests/viewer/test_visualization_ui.cjs`, 기존 graphviz/chevron geometry 검사, `tests/viewer/test_export.py`, `test_chevron_export_options.py`. 각 JS 파일의 실행 전제·runner는 해당 테스트를 읽고 확정한다.
- 수락 장면: 같은 source의 다른 operator, unavailable/partial/null, receipt 부재·충돌, layout 강제 실패, filter 적용 전후, 가로·세로 Chevron, HTML·지원되는 이미지/문서 export. 모든 지원 export에서 어떤 provenance가 포함/생략되는지 명시한다.
- 종료 기준: 브라우저에서 의미가 보존되고 묵시적 엔진 fallback이 없다. 실패 재실행이 통과해도 첫 실패를 기록하며 DOM 검증을 screenshot 존재로 대체하지 않는다.

### OC-PATCH-08 — 한도·sequence·근사 검증 자료

- 연결: OC-PLAN-05, P0-A1, P1-04/11/12/13.
- owner: `compute/variants.py`, `compute/object_conformance.py`, `case_centric/{context_ngrams,conformance_approximation}.py`는 읽기·재사용 우선. 새로운 계산 버그가 재현되지 않으면 제품 코드 수정 없음.
- 기존 exact variant 한도·공유 budget·unavailable order를 표로 연결한다. 비용 경계 근사는 독립 최적값 포함과 witness 검증을 유지하며 seed×subset 크기별 구간 폭·탐색 수·미해결 수를 측정한다. n-gram 선형화 반례는 02를 재사용한다.
- 실험 fixture·seed 목록·자원 budget은 실행 전에 고정하고 중단 결과도 기록한다. 시간/메모리를 측정하지 못하면 알 수 없음으로 둔다. 미사용 Hypothesis 도입이나 일반 sequence 엔진은 이번 패치의 기본 작업이 아니다.
- 테스트: `tests/compute/test_variants.py`, `tests/case_centric/test_context_ngrams.py`, `test_conformance_approximation.py`, 기존 object conformance oracle.
- 종료 기준: exact/경계 근사/통계 추정/탐색 중단의 해석이 구분되고 정상 empty success와 미완료를 구별한다.

### OC-PATCH-09 — 조건부 P1 변경 후보를 별도 확정

- 조사: object context 정의, OPERA annotation, replay silent/flooding, time/lifecycle/performance filter, ETOT/OTG 비교, OCCN↔OCPN 변환, lifecycle enrichment, OCEL 2.1 판본 차이.
- 코드/테스트: `object_centric/{performance,conformance,filtering,enrichment}.py` 및 `tests/object_centric/{test_performance,test_conformance,test_advanced_filtering,test_filter_predicates,test_graph_comparison,test_enrichment}.py`; 모델 변환의 실제 owner는 01에서 찾는다.
- 각 후보에 현재 profile, 참조 기대, 재현 fixture, 사용자 의미 판단, 호환 영향, 최소 파일을 기록한다. 새 알고리즘 필요/기존 정책 노출만 필요/문서만 필요/공백 없음으로 분류한다.
- 표준 비교는 실행 시 실제 2.1 판본을 확인하고 pre4 대비 breaking change를 구분한다. 최신본이 존재한다고 가정하지 않는다.
- 종료 기준: 근거 있는 후속 패치만 제안한다. 조사 완료를 계산 구현 완료나 참조 대체 검증 완료로 올리지 않는다.

### OC-PATCH-10 — 통합 검증과 인계

- 집중 검증 뒤 실제 영향 범위를 통합하고 전체 tests를 한 번 실행한다. 관련 codec·canonical golden·projection identity 회귀를 포함한다.
- 깨끗한 wheel 설치 후 저장소 밖 import/CLI/visualization smoke; 변경 Python Ruff check/format와 diff check; JS/browser·외부 corpus·extras는 별도 실행 범위를 기록한다.
- Python 3.10/개발 runtime/Windows/Linux/macOS는 실행·미실행 matrix로 남긴다. 기존 가상환경 실행 정책을 우회하거나 변경하지 않는다. 미실행을 skip 성공으로 바꾸지 않는다.
- 보고서: 실제 실행일, base SHA와 diff, 요구별 변경 파일·정의·반례·명령·결과, 첫 실패/재시도, 미실행 환경, codec/version 영향, 남은 의미 판단을 기록한다. 보고서 자신을 포함한 최종 diff hash를 보고서 안에 넣지 않는다.
- 종료 기준: 구현한 범위의 검증 근거가 연결되고, 추가 범위 미완료가 숨겨지지 않는다. 전체 대체·운영 준비 완료 선언은 별도다.

## 4. 실행 명령 계획과 사용자 검토 지점

아래는 후속 실행 템플릿이며 이번에 실행한 결과가 아니다. `python`은 당시 허용된 검증 runtime과 정확한 의존 경로로 치환하고 그 경로를 기록한다.

```powershell
python -m pytest tests/compute/test_ocdfg.py tests/object_centric/test_conformance.py tests/object_centric/test_case_projection.py tests/test_review_boundaries.py tests/case_centric/test_context_ngrams.py -q
python -m pytest tests/compute/test_ocpn_discovery.py tests/compute/test_variants.py tests/case_centric/test_conformance_approximation.py -q
python -m pytest tests/viewer tests/test_results.py tests/test_extended_results.py -q
python -m pytest tests -q
git diff --check
```

Ruff 대상 파일은 각 패치의 변경 Python 목록으로 제한한다. JS/browser의 정확한 실행 명령과 환경 변수는 기존 runner 확인 후 실행 기록에 남긴다. 전체 suite 실행이 opt-in browser/corpus까지 검증했다는 의미는 아니다.

사용자 검토는 02의 작은 로그·수치 정의, 05의 projection 해석, 07의 실제 화면에서 받는다. 이미 채택된 정의의 구현 수정은 매 commit마다 새 승인을 요구하지 않는다. 미정 의미에 대한 사용자 무응답은 승인으로 간주하지 않는다.

## 5. 유효기간·무변경 대안

이 계획은 고정한 코드/요구 판본에 유효하다. 코드·schema·표준 변경 또는 독립 반례로 전제가 깨지면 영향받은 패치의 정의·테스트·소비 경로를 재검토한다. 구현이 이미 충분한 패치는 실행 증거와 문서만 보강한다. 일정·공수·성능·전체 대체율은 아직 알 수 없음이다.

첫 실행 묶음은 **01의 대조표와 02의 집계·conformance 사례**다. 이 결과가 나온 후 03의 최소 표시 계약을 확정한다.
