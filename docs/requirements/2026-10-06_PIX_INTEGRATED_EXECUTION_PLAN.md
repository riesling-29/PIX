# PIX 통합 실행 인덱스 — 2026-10-06

기준: `feat/ocel-readers-v0.2.0` / `a0688f34e557c885c145051485072fd0623f263f`.
DOC-00 작업 브랜치: `docs/ocpm-plan-integration-20261006`. 이 문서는 원문·수정 결정·실행 작업을 연결한다. 새 알고리즘 계약이나 완료율을 선언하지 않는다.

## 적용 순서와 보존 범위

1. 명시된 사용자 선택과 [177개 공동 체크리스트](2026-09-18_PIX_REMAINING_177_JOINT_REVIEW_CHECKLIST.md)를 보존한다. ILP discovery는 공동 학습·설계 전 보류한다.
2. [9월 28일 Vera 답변의 ID별 결정](../reports/2026-09-28_OCPM_REQUIREMENTS_VERA_RESPONSE.md)과 [계획 변경안](2026-09-28_OCPM_DEVELOPMENT_PLAN_AMENDMENT.md)이 9월 27일 원문의 해당 수락 문구를 정정한다. 원문을 그대로 구현 지시로 사용하지 않는다.
3. 현재 코드·spec·테스트 근거는 [소비 계약](../specifications/PIX_OCPM_CONSUMPTION_CONTRACT.md), [도메인 사례](../user-guide/OCPM_DOMAIN_REVIEW_CASES.md), [기준점 인계서](../reports/2026-10-04_PIX_GITHUB_VALIDATION_HANDOFF.md)로 확인한다. 코드 존재·실행 통과·참조 대체 검증·사용자 도메인 수락은 서로 다른 상태다.
4. 세부 실행은 [NEXT-00~05 작업 카드](2026-10-04_PIX_PARALLEL_DEVELOPMENT_PLAN.md)를 따른다. 요구와 구현이 다르면 공백으로 기록하며 요구를 조용히 삭제하지 않는다.

## 문서 통합 출처

| 원문 | 고정 출처 | 처리 |
| --- | --- | --- |
| [검토헌장·PI/DS 부록](../audits/ALGORITHM_COMPLETENESS_REVIEW_CHARTER.md) | PR #1, `e1796ece1326558a893b2f7562db5ab6da9df36c` | Ashlar 합본·Provenance·Fathom의 236줄 전문 보존 |
| [OCPM 추가 요구](OCPM_추가개발_요구사항.md) | PR #2, `d8b36c86e54f626720adc335f064925ae6686e1f` | Provenance의 434줄 원문 보존 |
| [VIS 카피](reviews/2026-09-27_Gesso_OCPM_VIS_배지_툴팁_카피_초안.md) | 같은 PR #2·SHA | Gesso의 178줄 원문 보존; 당시의 '확정'에 후속 정정이 적용됨 |
| [VIS UX 리뷰](reviews/2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md) | 같은 PR #2·SHA | Gesso의 174줄 원문 보존 |

각 문서 앞에 현재 인덱스 안내를 추가했다. 원문의 trailing two-space Markdown 줄바꿈은 같은 의미의 backslash 줄바꿈으로 바꾸고 마지막 빈 줄을 정리했다. 그 외 본문은 원본과 대조해 보존했다. PR #2의 8줄 헌장 포인터 대신 PR #1 전문을 채택해 add/add 충돌을 해소했다. 기존 PR의 병합·종료·브랜치 삭제를 뜻하지 않는다. 원문의 담당자 승인은 당시 기록이며 이번 작업에서 새 승인을 받았다는 뜻이 아니다.

원문 `/workspace/PIX-audits/...CHARTER_MERGED.md`와 `/workspace/handoff-docs/...CHARTER.md` 대신 위 저장소 내 전문을 사용한다. `/workspace/PIX`는 원문의 코드 SHA로 확인한다. `PI_FOLLOWUP_SECTION_FOR_CHARTER.md`와 Schumpeter의 Ashlar baseline은 이번 통합 입력에 없으므로 **내용 미확인**이다. 이 파일들의 내용이나 승인을 추정하지 않는다.

## 요구 ID별 적용 기준과 다음 작업

아래 38행은 원문 ID의 추적표이며 완료표가 아니다. '수용'도 신규 구현 필요나 실행 통과를 뜻하지 않는다. 모든 행의 결정 근거는 위 9월 28일 답변 §3–4다.

| 원문 ID | 현재 적용 기준 | 다음 작업 |
| --- | --- | --- |
| OCPM-P0-01 | 기존 observational cardinality·witness·soundness 미입증 필드 재사용; 실패 payload에 필드 강제 금지 | NEXT-02 |
| OCPM-P0-02 | joint/object replay/flattened의 identity·모집단 구별; 수치가 같거나 다른 정상 사례 모두 허용 | NEXT-02/03 |
| OCPM-P0-03 | event pair/object/occurrence는 count 단위; 실제 비율에만 분모·0분모 정책 | NEXT-01/02 |
| OCPM-P0-04 | projection v2 receipt 재사용; 부재는 원본 대응 확인 불가이지 모든 KPI 무효가 아님 | NEXT-02 |
| OCPM-P0-05 | qualifier 선택·이력 as-of 사용·보존·미사용을 공개 연산별로 구별 | NEXT-01 |
| OCPM-P0-A1 | sequence/n-gram/subsequence/OC 부분순서를 구별; 새 패턴 엔진 자동 착수 아님 | NEXT-03 |
| OCPM-P1-01 | binding-prefix context의 모집단·분모·종료 계약 조사 | NEXT-01 |
| OCPM-P1-02 | OPERA annotation과 요약 통계를 구별하고 확인된 공백만 설계 | NEXT-01/02 |
| OCPM-P1-03 | silent closure·flooding 기존 정책과 한도 조사; 참조 동치 미확인 | NEXT-01 |
| OCPM-P1-04 | 기존 exact variant 동치·budget 검증을 추적; 신규 동형성 엔진 중복 개발 금지 | NEXT-03 |
| OCPM-P1-05 | time/lifecycle/performance filter의 실제 함수·경계 사례 대조 후 잔여 확정 | NEXT-01 |
| OCPM-P1-06 | ETOT/OTG 비교와 기존 OCDFG 비교의 지원 범위 대조 | NEXT-01 |
| OCPM-P1-07 | OCCN↔OCPN 각 방향의 변환·손실·표현 불가를 개별 확인 | NEXT-01 |
| OCPM-P1-08 | lifecycle first/last/singleton·기존 qualifier 충돌 테스트 재사용 | NEXT-01 |
| OCPM-P1-09 | 구현 pre4와 고정한 공식 판본의 필드별 차이 조사 후 변경 판단 | NEXT-01 |
| OCPM-P1-10 | 아래 VIS 세부 ID의 인덱스; 한 줄로 전체 화면 수락 처리 금지 | NEXT-02 |
| OCPM-P1-11 | 기존 n-gram·명시적 선형화 반례부터; 일반 sequential mining 지원 주장 금지 | NEXT-03 |
| OCPM-P1-12 | 입력 규모·예산·종료 이유·payload/evidence 범위 구별 | NEXT-03 |
| OCPM-P1-13 | OCEL collection 순열과 CaseLog recorded order 구별; 근사 비용 bound는 통계 CI가 아님 | NEXT-03 |
| OCPM-VIS-P0-01 | 뷰 종류·정의와 입력/연산 provenance를 현재 panel에 연결 | NEXT-02 |
| OCPM-VIS-P0-02 | raw count 단위·실제 비율 분모를 구별해 선택 값과 label 동시 표시 | NEXT-02 |
| OCPM-VIS-P0-03 | 관측성은 discovery provenance에 귀속; partial 원인·evidence 생략·invalid_input 구별 | NEXT-02 |
| OCPM-VIS-P0-04 | receipt·손실·공유 이벤트 요약; 출처 미확인과 KPI 계산 무효를 구별 | NEXT-02 |
| OCPM-VIS-P0-05 | 연산별 operator·모델·profile·모집단을 구별 | NEXT-02 |
| OCPM-VIS-P0-06 | 단위·미확정 값을 보존; unknown을 0으로 대체 금지 | NEXT-02 |
| OCPM-VIS-P0-07 | 렌더링/배치 실패를 계산 실패와 구별해 표시 | NEXT-02 |
| OCPM-VIS-P1-01 | 뷰 맵·교차 링크; 동일 source digest만으로 동일 분석 판정 금지 | NEXT-02 |
| OCPM-VIS-P1-02 | 화면 필터와 분석 모집단 변경을 구별; 규모별 성능은 측정 전 알 수 없음 | NEXT-02 |
| OCPM-VIS-P1-03 | annotation과 요약 통계·관측 구간·분모를 구별 | NEXT-01/02 |
| OCPM-VIS-P1-04 | 실제 지원하는 ETOT/OTG 비교 profile에만 범례 부여 | NEXT-01/02 |
| OCPM-VIS-P1-05 | 확인된 방향별 모델 변환 손실을 표시; 미지원 방향 위장 금지 | NEXT-01/02 |
| OCPM-VIS-P1-06 | 키보드·텍스트 대체·작은 화면·긴 한글/ID 검증 | NEXT-02 |
| OCPM-VIS-P1-07 | soundness·fitness·슬롯/시간·배치/인과 과장 금지; 투영을 '거짓'으로 표현하지 않음 | NEXT-02 |
| OCPM-P2-01 | feature/dataset 장기 백로그 보존; 사용자 미판정 확장 자동 승인 금지 | R08 후속 |
| OCPM-P2-02 | action impact 계산과 소비자 실행 분리 | R 후속·PI-01 |
| OCPM-P2-03 | 기존 revisable stream을 미구현으로 중복 계산하지 않음 | R 후속 |
| OCPM-P2-04 | intelligence/lineage 신규 의미는 별도 기획 | PI-01 후속 |
| OCPM-P2-05 | 기능·variant별 참조 대체 검증; 전체 일괄 승인 금지 | REP-01 |

## 첫 실행 묶음과 종료 조건

| 작업 | 산출물·종료 조건 | 남는 한계 |
| --- | --- | --- |
| DOC-00 | 전문 4개·38 ID·정정 우선순위·유효 링크를 통합 | 새 제품 검증이나 기존 PR 병합 아님 |
| NEXT-04 checker | Windows 조건부 tzdata 선언/설치 목록을 인정하고 예상 밖 runtime 의존성은 거부; 독립 wheel smoke 재실행 | 플랫폼 분기 단위 테스트를 Windows OS 실행으로 세지 않음 |
| NEXT-01 inventory | 공개 함수 위치·spec·입력 사용·결과·반례 연결, 미조사 행 명시 | 목록 존재만으로 전 함수 의미 감사 완료 아님 |
| NEXT-00 잔여 | 가능한 browser·지원 Python 셀 실행; 불가 셀은 이유와 함께 미검증 | 같은 SHA·환경 전체 suite를 이유 없이 반복하지 않음 |

이후 관련 정의가 확보된 NEXT-02/03 → 실제 통합 범위의 NEXT-05 → R01~R14 잔여와 REP-01 → 독립 출시 순으로 연결한다. 참조 fixture 준비는 앞단부터 가능하다. Schumpeter 효용 실험은 PIX 계산 검증·출시와 별도다. 기존 구현이 충분하면 제품 코드를 바꾸지 않는 것도 유효한 완료 방식이다.

현재 계획은 위 base 및 명시한 요구에 유효하다. API/profile/codec·표준 판본 변경, 독립 반례, 사용자 선택 변경 시 해당 행만 다시 연다. 공수·대규모 비용·전체 대체율은 알 수 없음이다. 문서 자신을 포함한 전체 diff hash를 본문에 최종 식별자로 쓰지 않으며 실제 commit은 Git에서 확인한다.
