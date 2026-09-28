# OCPM 계산·표시 계약 개발계획 변경

작성일: 2026-09-28. 상태: **계획 반영 결정 / 구현 미착수 / 개별 도메인 사례 미승인**.

근거: [Vera 답변서](../reports/2026-09-28_OCPM_REQUIREMENTS_VERA_RESPONSE.md). 코드 기준 `8a66984`, 외부 요구 기준 `d8b36c8`. 이 문서는 [상세 개발 계획](2026-09-13_PIX_DETAILED_DEVELOPMENT_PLAN.md)의 후속 변경이며 과거 계획·검증 기록을 덮어쓰지 않는다.

## 1. 범위 결정

이번 추가 작업은 기존 계산을 소비자가 올바르게 해석하도록 명세·결과·시각화를 연결하는 것이다. 기존 177개 선택, ILP 보류, PM4Py/OCPA 전체 대체 지향, 수집은 Agent·계산은 PIX 원칙을 유지한다. 같은 의미의 registry·envelope·계산 엔진을 새로 만들지 않는다.

확정 반영: OCPM-P0-01…05, P0-A1, VIS-P0-01…07의 수정된 수락 기준; 기존 구현의 증거 연결; P1의 명세·공백 조사와 VIS 개선 계획. 조건부 P1 계산 확장은 독립 반례로 공백을 확인한 후 범위를 확정한다. P2는 후속 백로그이며 이번 착수 대상이 아니다.

새 ID `OC-PLAN-*`는 계획 추적용이다. 기존 runtime operator/version이나 요구 registry ID를 대체하지 않는다.

## 2. 단계별 작업과 완료 조건

### OC-PLAN-01 — 기존 지원과 실제 공백의 구분

원문 연결: P0-01…05, P1-01…09, P1-12. 기존 계획 연결: SCOPE-01/02/03.

먼저 요구별로 함수 → profile → 결과 필드 → 기존 테스트 → 잔여 공백을 작성한다. “구현 존재”, “해당 profile 검증”, “참조 라이브러리 대체 검증”, “Skill 사용 허용”은 별도 열이다. partial 행 수를 개발 물량으로 환산하지 않는다.

산출물은 OC 지원·한도표와 qualifier/history 사용표다. existing OCPN issues, OCDFG count fields, projection v2, variant budget, n-gram을 재사용 대상으로 표시한다. 같은 의미가 충족되면 코드 수정 없이 완료한다. P1-05…08의 추가 알고리즘은 이 표에서 공백이 확인되기 전에는 구현 목록으로 확정하지 않는다.

완료 조건: 원문 P0/P1 ID마다 확인한 코드·테스트 또는 미확인 사유가 있고, 신규 작업과 이미 충족한 요구가 분리되어 있다.

### OC-PLAN-02 — 도메인 검토용 작은 사례와 의미 명세

원문 연결: P0-02/03/05/A1, P1-01/11/13. 기존 계획 연결: SCOPE-02 및 도메인 검토 절차.

사용자에게 코드 대신 다음 표를 제시한다: 사건·시각·참여 객체·qualifier → 계산 질문 → 손계산 기대값 → 제외·미확정 이유. 정상·경계·반례·정보 부족 사례를 구분한다.

| 사례 | 기대하는 확인 | 재사용할 테스트 위치 |
| --- | --- | --- |
| 같은 A→B 이벤트 쌍을 객체 둘이 공유하고 한 객체는 A→B를 반복 | 고유 이벤트 쌍·고유 객체·객체별 발생 수가 각각 다름; qualifier 중복은 발생 수를 늘리지 않음 | `tests/compute/test_ocdfg.py` |
| 공유 이벤트 제약 위반 및 단순 완전 적합 로그 | 차이가 나는 joint/flattened 반례의 각 독립 기대값; 값이 같은 정상 사례에서도 operator 구별 | `tests/object_centric/`의 기존 conformance 테스트 조사 후 확장 |
| 한 이벤트가 여러 투영 case에 등장 | 원본 ID 대응·그룹·split 누출; 자원 공유만으로는 같은 누출 판정 안 함 | `tests/test_review_boundaries.py`, `tests/object_centric/test_case_projection.py` |
| OC 부분순서를 서로 다른 선형화 정책으로 n-gram화 | 선택한 모집단·순서에 따라 패턴이 달라짐; OC 원본의 새 인과 발견으로 주장하지 않음 | `tests/case_centric/test_context_ngrams.py` |
| event/object/E2O collection 순열 및 recorded-order CaseLog 재배열 | 전자는 동일 canonical 의미의 불변성; 후자는 의미가 바뀔 수 있음 | 기존 compute permutation 테스트 |

golden은 위 독립 기대값을 근거로 만든다. 현재 구현 출력이나 hash만 복사하여 oracle로 삼지 않는다. 부등값만으로 conformance의 정확성을 승인하지 않는다. 계산 의미가 새로 결정되는 항목은 [도메인 검토 절차](2026-09-13_PIX_DOMAIN_REVIEW_WORKFLOW.md)를 따르며 사용자 판단을 추정해서 채우지 않는다.

완료 조건: 집계 단위와 비율 분모가 구분되고, 각 사례의 수식·모집단·동률·결측·비용 정책이 명확하다. 독립 기대값이 미정인 수치 항목은 보류하며 다른 항목을 막지 않는다.

### OC-PLAN-03 — 기존 결과·receipt와 표시 metadata 연결

원문 연결: P0-01/03/04, VIS-P0-02…06. 기존 계획 연결: SCOPE-03/04, VIEW.

변경 후보 owner: `src/pix/viewer/visual_object_adapters.py`, 관련 viewer contracts/adapters, `src/pix/object_centric/case_projection.py`. 실제 변경 파일은 01·02 결과로 최소화한다.

- OCDFG가 이미 제공하는 세 count를 그대로 사용한다. 선택한 표시 metric의 정의를 노출하며 원시 count 전체를 denominator라 명명하지 않는다.
- projection `describe()`와 grouping을 연결한다. 그룹 기준은 원본 이벤트 공유이며 객체 참여 횟수나 자원 연결성과 혼동하지 않는다. receipt 없는 소비자 화면은 출처 미확인으로 표시한다.
- OCPN 관측성·soundness 미입증은 실제 discovery provenance로부터 읽는다. 임의 OCPN 입력에 동일 배지를 붙이지 않는다.
- computed/partial/unavailable/invalid_input 의미를 유지한다. 계산 미완료, 모집단 제외, evidence 생략, 표시 오류, layout 오류를 구별한다.
- source digest만으로 서로 다른 selection/profile/model 분석을 같은 결과로 연결하지 않는다. 기존 computation·parent·model identity를 재사용한다.

완료 조건: 관련 결과 저장/복원과 viewer 변환에서 의미가 보존된다. 기존 canonical V1, projection v2 identity, result/model codec를 이유 없이 변경하지 않는다. 새 필드가 필요하면 old document 읽기·unknown schema 진단·version 영향 검토를 먼저 기록한다. 원본 provenance를 canonical digest에 일괄 혼합하지 않는다.

### OC-PLAN-04 — 화면·내보내기의 의미 검증

원문 연결: VIS-P0-01…07, VIS-P1-01…07, P1-10. 기존 계획 연결: VIEW 및 Graphviz/Chevron 요구.

Graphviz WASM·Chevron·VisualizationDocument를 확장한다. 새 layout 엔진은 도입하지 않는다. joint/object replay/flattened를 별도 패널로 표시하고 metric 단위·미확정·관측성·투영 조건을 제공한다. 큰 그래프의 표시 필터와 실제 계산 모집단 변경을 구별한다. 색만으로 상태를 전달하지 않으며 키보드 선택·텍스트 대체를 점검한다.

Gesso 카피는 답변서의 수정안을 적용한다. partial 문구는 원인을 반영하고 projection 배너는 원본 전체를 표현하지 않는다는 구체적 제한을 설명한다. Chevron 슬롯은 시간이 아니며 layout 좌표는 인과·병목 계산이 아니다.

검증: 기존 `tests/viewer/`의 adapter/serialization/browser 검사를 확장한다. 정상·partial·unavailable·invalid input·receipt 부재·layout 실패·evidence 생략 사례를 화면과 export에서 대조한다. 실제 browser를 실행하지 못하면 미실행으로 기록한다. pixel 일치 대신 표시 값·범례·identity·실패 상태를 핵심 oracle로 삼는다.

완료 조건: 공개 샘플의 숫자·배지·툴팁·손실 설명이 동일한 계산 정의를 가리킨다. 실패 시 묵시적 layout fallback이 없고 unknown을 0으로 표시하지 않는다.

### OC-PLAN-05 — 한도·근사 품질 및 실제 잔여 P1 확정

원문 연결: P1-02…09/11…13. 기존 계획 연결: 계산 profile 검증·참조 대체 평가.

입력 규모(|E|, |O|, type, E2O), 탐색 budget, 종료 이유, 반환 가능한 payload/evidence를 정리한다. 기존 variant exact budget 테스트를 우선 재사용한다. 비용 경계 근사는 독립 최적값 포함과 witness를 검증하고 seed×subset 크기에 따른 구간 폭·계산량·미해결 수를 별도 측정한다. 통계적 모집단 추정 주장이 없는 경로에 CI를 일괄 요구하지 않는다.

object-type ablation은 모든 지표가 단조라는 가정을 두지 않는다. 어떤 함수·선택·정규화에서 어떤 방향성이 성립하는지 먼저 명세한다. Hypothesis는 공백과 유지 비용에 따라 선택하며 채택 자체를 정확성 gate로 삼지 않는다.

OCEL 2.1은 기준 pre4와 조사 시점에 확인한 표준 판본을 고정해 차이표부터 작성한다. OPERA·replay·filter·ETOT/OTG·모델 변환·enrichment는 기존 지원과 달리 필요한 행동 및 독립 반례가 확인된 항목만 다음 구현 묶음으로 확정한다.

완료 조건: 실행한 실험의 runtime/fixture/profile/command/result와 미실행 범위를 남긴다. 대규모 성능·최소 Python·OS 검증을 실행 없이 통과로 표시하지 않는다. 기존 full suite 수치를 새 결과로 재사용하지 않는다.

## 3. 순서·협업·보고

실행 순서는 01 → 02 → 03 → 04이며 05의 기존 한도 조사·테스트 목록화는 01과 독립적으로 가능하다. 새 공유 schema와 미정 의미에 의존하는 구현은 해당 정의가 결정된 뒤 진행한다. 이번 commit은 문서만이며 제품 구현 착수 기록이 아니다.

다음 구현 묶음 시작 시 실제 브랜치와 수정 경로를 명시한다. 코드 PR 전에 공유 계약·파일 충돌 정보를 개발팀에 전달할 준비를 하며, 이번 문서 작성이 이미 전달·합의되었다고 기록하지 않는다. 사용자 또는 승인된 통신 경로를 통한 전달은 별도다. Schumpeter receipt 신선도 문제는 별도 저장소 작업으로 분리하며 PIX 변경으로 우회하지 않는다.

각 묶음은 요구 ID → 정의/profile → 함수 → 독립 기대값 → 실제 실행 → 한계로 보고한다. 도메인 승인과 구현·테스트 상태는 별도 열로 유지한다. 새 알고리즘이나 전역 version 변경은 표면 통일을 이유로 추가하지 않는다.

## 4. 유효기간·철회와 이번 산출물

이 계획은 위 기준 SHA와 사용자 요구 경계에서 유효하다. 독립 반례·후속 코드·표준·codec 변경이 발견되면 영향받은 단계만 재검토한다. 기존 구현이 요구를 충족하면 무변경을 선택한다. 예상 공수·완료일·전체 대체율·실무 성공률은 알 수 없음이다.

이번 산출물은 답변서, 이 계획, 기존 상세 계획의 후속 링크다. 신규 제품 테스트와 기능은 추가하지 않았다. 문서 경로·diff 공백·staged 범위를 검사하고 문서만 커밋한다.
