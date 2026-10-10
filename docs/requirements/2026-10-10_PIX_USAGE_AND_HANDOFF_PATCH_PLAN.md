# PIX 마무리와 실사용 개선 패치 플랜

작성일: 2026년 10월 10일 KST  
대상: minero 선생님과 PIX 개발 담당  
상태: 20%를 variant 개수 비중으로 확정하고 사용자 승인에 따라 실행 중. 구현과 검증 기록은 저장소의 2026-10-10_PIX_VARIANT_CATALOG_HANDOFF.md 및 PR #8을 따른다.

PIX의 현재 구현을 재현 가능한 사용 기준점으로 정리하고, 실사용에서 드러나는 필요에 따라 개선한다. 대표 Trace 선정 알고리즘은 지금 확정하지 않는다. Schumpeter로 개발 중심을 옮기는 데 필요한 최소 마무리와, 이후 계속할 PIX 검증·확장을 구분한다. 전체 기능 완성이나 참조 구현 대체 인증을 전환 조건으로 삼지 않는 것이 이 계획의 제안이다.

## 1. 확인된 기준과 이번 대화의 결정

### 1.1 저장소 기준

2026년 10월 10일 원격 조회 기준이다. 구현 작업을 시작할 때 두 브랜치의 변경 여부를 다시 확인한다.

| 항목 | 확인한 상태 | 계획에 미치는 영향 |
| --- | --- | --- |
| 저장소 | Chanta-Research-Group/PIX | 이전 개인 계정 경로를 새 작업의 기준으로 사용하지 않음 |
| main | 2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3 | 이전 개발분 통합 기준 |
| work | b343a5bee613ec243848432c98a4e51843c9e17a | 그룹별 대표 Trace 비교 구현 포함 |
| main 대비 work | ahead 1, behind 0, 변경 파일 19개 | 대표 비교는 신규 구현보다 통합이 먼저 |
| CI | 조회한 work 전체 tree에 .github/workflows 없음. main과의 19개 변경에도 해당 경로 없음 | 자동 검증은 별도 후속 작업 |
| 패키지 선언 | 0.5.0, Python >=3.10, Windows 조건부 tzdata | 이 값 자체가 출시·모든 환경 검증 완료를 뜻하지 않음 |

기존 10월 4일 계획의 “main은 개발 기준이 아님”은 당시 기록이다. 이후 main 통합 상태를 최신 안내에 반영하되, 과거 검증 보고서의 기준 SHA와 결과를 소급해서 바꾸지 않는다.

### 1.2 현재 비교 기능과 한계

이미 구현된 범위는 라벨 또는 명시적 case 목록에 따른 그룹 구성, 최빈 활동 순서의 실제 case를 기본 대표로 선택, 수동 대표 지정, 한 화면의 다중 그룹 비교, 기준·후보 변경, 차이 필터, SVG 저장이다.

| 구분 | 현재 계약 |
| --- | --- |
| 기본 후보 | 그룹당 3개. 후보의 빈도와 후보들이 설명하는 case 수를 보존 |
| 대표 | 그룹별로 선택한 실제 case 하나. 평균·합성 Trace가 아님 |
| 비교 | 기준 대표와 각 대상 대표를 독립적으로 정렬 |
| 순서 | CaseLog의 기록 순서. OCEL은 명시적 case 투영을 거침 |
| 라벨 편집 | HTML에서 원 로그 라벨을 변경·저장하는 기능 없음 |
| 자원 한도 | 전체 후보 기본 64개, pair 기본 1,000,000 DP cells, 방향별 pair 합산 기본 4,000,000 cells |
| 브라우저 | 사전 계산된 후보와 정렬 증거를 선택. 새로운 mining을 실행하지 않음 |

10월 7일 구현 보고서에는 Linux Python 3.10.21 및 3.12.14 각각 10,597 passed, 41 skipped, 1,169 subtests passed, Node 48 passed, 실제 Chromium 비교 화면 1 passed와 5개 흐름, 독립 wheel 검증 통과가 기록돼 있다. 이는 그 작업의 기록이며 이번 계획 작성에서 다시 실행한 결과가 아니다. 해당 비교 화면 검증을 전체 OCPM 화면 검증으로 확대하지 않는다.

### 1.3 사용자 결정과 계획상 제안

| 항목 | 이번 대화에서 확인된 내용 | 처리 |
| --- | --- | --- |
| 실무 분석 방식 | value_counts()처럼 Trace를 빈도순으로 나열하고 주요 범위를 함께 봄 | 빈도·비율·누적 비율·복수 선택을 후속 요구로 보존 |
| 대표 선정 | 방법이 여러 개이므로 추가 고민 필요 | 현재 최빈·수동 방식을 유지하고 새 선정 알고리즘 보류 |
| 주요 공통 노드 | 대표 선정 기준의 실무 후보 | 노드 의미·반복 occurrence·경로 차이가 드러나는 예제로 후속 검토 |
| 차이 표시와 사용 흐름 | 실제 써보면서 평가 | 미수락 상태를 보존하되 기술 검증과 분리 |
| 다음 개발 중심 | PIX를 사용하면서 Schumpeter 쪽으로 이동 | 아래 최소 마무리 후 전환하는 실행 순서를 제안 |
| 사용자 확정 | 20%는 빈도순 고유 variant 개수 비중 | ceil(V × p / 100)개 선택, case coverage 별도 표시 |
| 실행 승인 | 가능한 작업 바로 진행 | F01/F02 빈도 표와 복수 sequence 행 포함 |
| 미결정 | 추가 집계·정렬 표현, 브라우저 라벨 편집 필요 | 실사용 후 검토 |

기본 선택은 고유 variant 개수의 상위 20%다. 올림과 기존 활동 tuple 사전순, 빈도 표와 복수 원 sequence 행은 이번 구현의 명시적 선택이다. 사용자 의도와 다른 실제 사례가 나오면 해당 항목만 다시 조정한다.

## 2. 작업 순서와 범위

| 순서 | 패치 | 내용 | 시점과 기존 계획 연결 |
| --- | --- | --- | --- |
| 1 | P00 | 최신 기준·사용자 결정·미완료 목록 정리 | 전환 전. 통합 실행 인덱스 갱신 |
| 2 | P01 | 기존 work 비교 기능의 main 통합 | 전환 전. NEXT-05의 실제 통합 범위 |
| 3 | P02 | 재현 가능한 비교 예제와 사용 점검 묶음 | 전환 전. NEXT-02 및 NEXT-05 일부 |
| 4 | P03 | 사용 경로의 설치·wheel·계산·화면 확인 | 전환 전. NEXT-00/04 일부 |
| 5 | P04 | PIX 사용 기준점과 Schumpeter 인계 | 전환 전. R14 경계 문서 |
| 이번 실행 | F01 | 빈도 목록과 상위 variant 개수 비중 선택 | 사용자 실행 승인. R02/R08/R13 |
| 이번 실행 | F02 | 선택한 여러 Trace를 함께 보는 화면 | F01과 함께 실행. NEXT-02/R13 |
| 조건부 | F03 | 브라우저 라벨·그룹 편집과 저장 | 필요가 확인될 때 별도 설계 |
| 병행·후속 | V01~V04 | 기존 의미 감사·UI·알고리즘·환경 검증 | NEXT-01~05와 REP-01을 보존 |
| 보류 | H01~H02 | 새 대표 선정과 ILP discovery | 사례 검토 또는 공동 학습·설계 후 |

기본 실행 순서는 P00 → P01 → P02 → P03 → P04다. 설치 문제 등 재현된 결함은 영향을 받는 단계보다 먼저 수정한다. F01/F02, 전체 150개 입력 의미 감사, 모든 OS 조합, R01~R14 전체 완료를 Schumpeter 전환의 선행 조건으로 추가하지 않는다. 다만 Schumpeter가 실제 소비할 계산 경로에서 확인된 결함은 해당 연동 경로의 차단 사유가 된다.

모든 패치는 결함이 없고 기존 구현이 요구를 충족하면 코드 변경 없이 근거와 문서만으로 종료할 수 있다.

## 3. 전환 전 패치 카드

### P00 최신 기준과 미완료 작업 정리

목적: 과거 계획의 상태 표기 때문에 구현 완료 항목을 다시 개발하거나, 검증 잔여를 삭제하는 일을 막는다.

변경 대상:

- README.md의 현재 개발 기준과 비교 기능 진입 안내.
- docs/requirements/2026-10-06_PIX_INTEGRATED_EXECUTION_PLAN.md에 최신 실행 계획 연결.
- 새 문서 제안: docs/requirements/2026-10-10_PIX_USAGE_AND_HANDOFF_PATCH_PLAN.md.
- 과거 실행계획에는 필요하면 최신 문서 포인터만 추가하고, 당시 사실과 검증 수치는 보존.

작업:

1. 실행 시 main/work SHA와 차이를 다시 읽는다.
2. “구현됨 / 통합 대기 / 기술 검증 잔여 / 실사용 검토 / 설계 보류”를 분리한다.
3. 기존 177개 사용자 선택과 38개 OCPM 요구 ID를 지우거나 완료로 일괄 처리하지 않는다.
4. 대표 선정·공통 노드·라벨 편집을 별개의 결정으로 남긴다.

완료 조건: 현재 기준, 다음 작업, 보류 이유가 한 문서에서 추적되고 과거 보고서와 모순되지 않는다. 문서만 변경되면 전체 제품 테스트를 새로 만들거나 반복하지 않는다.

### P01 대표 Trace 비교 기능 통합

목적: work에서 구현된 기능을 실제 사용할 main 기준에 반영한다.

대상: 현재 main...work의 19개 변경 파일. 핵심 파일은 다음과 같다.

- src/pix/case_centric/trace_comparison.py
- src/pix/viewer/visual_case_adapters.py, visual_contracts.py, visual_serialization.py
- src/pix/viewer/assets/visualization.js, visualization.css
- tests/case_centric/test_trace_comparison.py
- tests/browser/test_trace_comparison_browser.py
- docs/user-guide/TRACE_GROUP_COMPARISON_GUIDE.md
- examples/trace_group_comparison_demo.py

작업:

1. 현재 차이가 여전히 해당 기능 커밋인지 확인한다. 다른 개발자의 변경이 생겼으면 실제 통합 범위를 다시 정한다.
2. 기존 schema·registry·lazy API 연결과 projection 관련 변경을 검토한다.
3. 실제 통합 diff에 맞는 집중 검증과 codec 회귀 검증을 수행한다.
4. 일반 병합으로 main에 반영하고 통합 SHA를 기록한다. work를 삭제하거나 강제 재설정하지 않는다.
5. 이미 다른 작업에서 병합됐다면 변경을 중복 적용하지 않고 P01을 종료한다.

완료 조건: main에서 비교 예제의 공개 진입점이 작동하고, 원 case/event ID·빈도·unknown·투영 근거가 보존된다. 공통 계산 또는 codec에 의미 있는 변경이 있을 때는 해당 회귀 범위를 넓힌다.

제외: 후보 수를 늘려 누적 80% 탐색을 흉내 내기, 대표 선정 규칙 변경, 브라우저 라벨 편집 추가.

### P02 비교 예제와 실사용 점검 묶음

목적: 선생님이 개발 문서를 해독하지 않고 실제 화면으로 판단할 수 있게 한다.

기존 파일을 우선 확장한다.

- examples/trace_group_comparison_demo.py
- docs/user-guide/TRACE_GROUP_COMPARISON_GUIDE.md
- tests/case_centric/test_trace_comparison.py
- tests/browser/test_trace_comparison_browser.py
- 새 기록 양식 제안: docs/reports/2026-10-10_PIX_USAGE_FEEDBACK.md

예제 구성:

| 예제 | 확인할 의미 | 기대 결과 |
| --- | --- | --- |
| 정상·재작업·검사 생략 | 추가·누락·반복과 원 event ID | 차이를 해당 원본 occurrence까지 확인 가능 |
| 한 그룹에 여러 빈도 variant | 최빈 대표와 그룹 전체의 차이 | 대표 빈도와 후보 coverage를 그룹 전체 분모로 표시 |
| 최빈 후보 밖의 수동 대표 | 실제 중요 사례의 선택 | 기존 계약대로 후보에 포함되고 원 variant 빈도 유지 |
| 빈 그룹·빈 Trace·라벨 없음 | 세 상태를 서로 구별 | 빈 그룹은 대표 없음, 빈 Trace는 실제 빈 sequence, 미라벨 case는 unassigned |
| 한도에 걸린 pair | 미계산과 일치의 구별 | 비용을 0으로 만들지 않고 기존 미계산 상태를 표시 |

기존 테스트로 충분한 예제는 재사용한다. 후보 간 삽입이 같은 열에 있다는 이유만으로 서로 대응한다고 표시하지 않는지, 차이 필터가 원 데이터와 집계 분모를 바꾸지 않는지도 점검한다.

산출물: 합성 입력, 실행 명령, 원 계산 JSON, 시각화 JSON, 독립 HTML, 필요한 화면 증거. 각 결과를 만든 SHA와 실행 환경을 기록한다.

사용자 피드백은 “입력/선택 상태 → 기대한 해석 → 실제 표시 → 업무 영향”으로 남긴다. 대표가 적절한지, 중요한 차이가 보이는지, 라벨 편집이 필요한지는 실사용 중 판단한다. 응답을 아직 받지 못해도 “도메인 수락 대기”로 두며 전체 작업을 멈추지 않는다.

완료 조건: 작은 예제를 한 번의 안내된 실행으로 열 수 있고 기술적으로 확인할 기대값과 사용자에게 물을 해석이 분리된다.

현재 저장소 루트에서 재사용할 명령은 아래와 같다. 패치 실행 시 해당 통합 SHA의 환경에 설치한 뒤 사용하며, 이 계획 작성 중 실행한 명령은 아니다.

```bash
python -m pytest tests/case_centric/test_trace_comparison.py tests/test_mining_serialization.py -q
node --test tests/viewer/test_visualization_ui.cjs
python examples/trace_group_comparison_demo.py --output .artifacts/trace-group-comparison
```

실제 브라우저 검사는 tests/browser/README.md의 opt-in과 Playwright 설정을 따른다. 이미 생성된 산출물을 교체하는 경우에만 예제의 --overwrite 옵션을 사용한다.

### P03 실제 사용 경로의 최소 검증

목적: 사용 가능한 기준점을 설치·실행 근거와 함께 인계한다.

대상:

- pyproject.toml과 기존 tools/check_*wheel.py 중 실제 관련 checker.
- tests/test_wheel_environment.py
- 비교 계산·codec·Node·실제 브라우저 검증.
- 새 보고서 제안: docs/reports/2026-10-10_PIX_USAGE_BASELINE_VALIDATION.md

검증 범위:

1. 현재 통합 SHA, OS/Python/Node, 의존성, source 설치인지 wheel인지 기록한다.
2. source tree 밖의 새 환경에서 wheel import, 비교 계산, JSON roundtrip, HTML 생성, 포함된 viewer asset을 확인한다.
3. 실제 브라우저에서 기준·대표·그룹·차이 필터 변경과 SVG 저장을 확인한다.
4. 사용자 사용 환경인 Windows의 최소 사용 경로를 우선 확인한다. 현재 실행 환경에서 불가능하면 복사해 실행할 명령과 미검증 범위를 인계하고, 통과로 기입하지 않는다.
5. 전체 suite 재실행 여부는 통합 변경과 기존 증거의 적용 범위로 결정한다. 같은 코드·환경의 충분한 증거를 이유 없이 반복하지 않는다.

실패한 설치·계산·내보내기는 최소 재현 후 별도 수정 커밋으로 처리한다. 실제 이용 경로에 치명적인 실패가 남으면 그 경로를 사용 가능으로 선언하지 않는다. 이용하지 않는 OS·optional backend의 미검증은 기록하고 후속 V04로 보낸다.

CI workflow 도입은 V04다. CI가 아직 없다는 이유로 재현 가능한 수동 검증 결과를 무효로 만들지 않는다.

### P04 사용 기준점과 Schumpeter 인계

목적: PIX 전면 완성을 기다리지 않고, 검증한 계산 범위를 Schumpeter 개발에서 재사용할 수 있도록 한다.

새 문서 제안: docs/reports/2026-10-10_PIX_SCHUMPETER_HANDOFF.md.

인계에 반드시 포함할 내용:

- 사용할 PIX commit과 wheel hash, 설치 및 예제 실행 명령.
- 검증한 입력 형식·공개 연산·spec/profile·출력 계약.
- source digest, computation identity, case/event/object ID, projection receipt를 어디서 확인하는지.
- computed/partial/unavailable/invalid_input 및 기존 issue·종료 사유의 소비 방법.
- 테스트 실행·skip·미실행 환경과 실사용 피드백 대기 항목.
- 후속 F/V/H 작업과 해당 기능에 직접 영향을 미치는 알려진 결함.
- “전체 PM4Py/OCPA 대체 검증 완료”나 “전체 OCPM 수락 완료”로 해석할 수 없다는 지원 범위.

Schumpeter 쪽 첫 연동 작업의 제안 범위는 “저장된 소규모 이벤트 fixture → 명시 mapping → PIX 계산 → 구조화된 결과 소비”다. 최신 Schumpeter 코드와 이미 존재하는 adapter를 먼저 확인한 뒤 구체적인 수정 파일을 정한다. 이 계획은 Schumpeter의 현재 미구현 상태를 단정하지 않는다.

책임은 다음과 같이 유지한다.

| 책임 | PIX | Agent와 Schumpeter |
| --- | --- | --- |
| 입력 | mapping 검증, canonical 데이터 수용, 원본 대응 보존 | 수집·계측·인증·자료 취득 |
| 분석 | 계산과 근거·결과 상태 반환 | 목적·분석 대상·실행 정책 선택 |
| 실행 | 계산 결과와 진단 | LLM 호출, 도구 실행, 재시도, 최종 행동 결정 |
| 복구 | 해당 계산의 revision·snapshot 계약 | 지속 저장, 전달·재전달, 운영 관리 |

의존 방향은 Schumpeter → PIX다. PIX에 Schumpeter runtime import를 추가하지 않는다.

완료 조건: 담당자가 위 기준점을 설치하고 같은 입력으로 결과를 재현하며, 미검증 항목을 알고 다음 작업을 시작할 수 있다.

## 4. 이번 실행의 Trace 탐색 패치

### F01 빈도 목록과 상위 variant 개수 비중 선택

착수 조건 충족: 사용자가 variant 개수 비중을 확정하고 가능한 작업의 실행을 승인했다. 대표 선정 알고리즘의 확정을 기다릴 필요는 없다.

기본 설계안:

- 입력은 CaseLog, 명시적 그룹 또는 라벨 속성, 기존 CaseTraceSpec이다.
- 동일한 활동 tuple을 하나의 variant로 묶는다. 순서와 반복을 보존한다.
- 그룹별 모든 variant의 건수·비율·누적 비율·구성 case ID를 계산하는 목록과, 그 목록에서 선택한 집합을 구별한다.
- 기존 case sequence 집계 경로를 조사해 재사용한다. 현재 trace_comparison.py의 후보 축약 전에 있는 그룹화는 재사용 후보다.
- src/pix/compute/variants.py는 OC event-object 구조의 exact variant 계산이다. 이를 활동열 빈도 목록과 같은 연산으로 대체하거나 이름만 재사용하지 않는다.
- 기존 비교 결과 schema를 조용히 바꾸지 않는다. 필요하면 별도 result/operator와 기존 registry·codec 등록을 추가한다.

구현 위치 제안: 새 src/pix/case_centric/trace_catalog.py와 대응 tests/case_centric/test_trace_catalog.py. 새 파일 생성 여부와 공개 함수명은 기존 집계 API 중복 확인 후 확정한다.

집계와 선택 계약의 제안:

| 항목 | 규칙 |
| --- | --- |
| 분모 N_g | 명시적으로 선택한 분석 모집단 안에서 해당 그룹에 속한 case 수 |
| 빈도 n_i | 해당 variant의 case 수. event 수·활동 수가 아님 |
| 비율 | n_i / N_g. 표시 반올림과 원 count를 분리 |
| 누적 비율 C_k | 빈도 내림차순 목록의 1번부터 k번까지 건수 합 / N_g |
| 정렬 동률 | 활동 tuple 사전순으로 결정. 동률 variant를 표에서 식별할 수 있게 함 |
| variant 개수 선택 | 고유 variant 수 V_g와 정수 p(0~100)에 대해 ceil(V_g × p / 100)개 선택 |
| 경계 동률 | 기존 활동 tuple 사전순으로 정확히 k개 선택. 동률 전체 추가 안 함 |
| 올림 | 요청 p와 실제 선택 variant 비중 k/V_g를 구별. case coverage는 별도 지표 |
| 수동 선택 | 빈도와 무관하게 variant 추가·제외 가능. 실제 coverage를 다시 계산 |
| 빈 그룹 | 분모 0, 비율은 해당 없음. 0%나 100%로 확정하지 않음 |
| 빈 Trace | 하나의 유효한 빈 sequence. 불완전 입력을 빈 Trace로 바꾸지 않음 |
| 미라벨 | unassigned로 별도 집계. 정상/비정상 중 하나로 자동 편입하지 않음 |
| 화면 필터 | 행 숨김·검색만으로 분모와 원 frequency를 바꾸지 않음 |
| 분석 모집단 변경 | 새 계산으로 취급하고 source·filter·group/spec identity를 갱신 |

20%는 **variant 개수 비중**으로 확정됐다. case 누적 비율은 표의 참고 지표이며 선택 임계값이 아니다.

| 빈도 분포 | 선택 | 기대 결과 |
| --- | --- | --- |
| 60, 20, 10, 5, 5 / 100 cases | 상위 20% variants | 1/5 variants, 60/100 cases |
| 같은 분포 | 상위 80% variants | 4/5 variants, 95/100 cases |
| 7 variants | 상위 20% variants | ceil(1.4)=2개, 실제 약 28.57%; case coverage 별도 |
| 5 variants | 0% / 100% | 0개 / 5개 |
| 경계 동률 | 상위 k개 | 활동 tuple 사전순, 동률 전체 추가 안 함 |
| A→B→A와 A→A→B | 빈도 집계 | 서로 다른 variant |
| 크기가 다른 그룹 | 각각 상위 20% | 각 그룹 고유 variant 개수를 분모로 함 |

수락 조건:

- 선택된 모든 variant의 case 집합을 합친 수가 보고한 coverage와 일치한다.
- full catalog의 counts 합은 해당 그룹 분모와 일치한다. 목록이 불완전하면 완전한 상위 variant 비중 선택이라고 주장하지 않는다.
- 결정적 정렬, 빈 그룹·빈 Trace·누락 라벨·비정상 입력·반올림 경계를 확인한다.
- JSON 왕복 후 identity·counts·membership·선택 정책이 보존된다.
- 기존 그룹별 대표 비교 API와 결과의 의미가 유지된다.

후보·정렬 한도와의 관계: 빈도 목록을 계산하는 것과 모든 후보 쌍을 정렬하는 것을 분리한다. 사전 계산 후보 한도를 올려 catalog 기능을 대신하지 않는다. 저장·표시·정렬 중 어느 한도에 걸렸는지 별도로 드러내고, 생략된 variant를 분모에서 조용히 제거하지 않는다.

### F02 복수 Trace의 비교 화면과 내보내기

선행 조건: F01 집계 계약과 아래 “합쳐보기” 표현의 범위를 작은 예제로 검토한다.

| 표현 후보 | 보여주는 것 | 주의할 점 |
| --- | --- | --- |
| 빈도 표와 복수 sequence 행 | 선택한 variant들의 원 활동열과 빈도 | 행 수가 많으면 탐색·표시 한도 필요 |
| 선택 집합의 집계 DFG | 선택한 case 집합의 활동·간선 빈도 | 개별 경로의 결합 관계를 원 Trace와 동일하게 해석할 수 없음 |
| 기준 Trace에 대한 복수 정렬 행 | 각 선택 variant와 기준의 차이 | 공동 최적화한 multi-alignment가 아님 |

1차 구현안은 빈도 표와 복수 sequence 행이다. 집계 DFG 및 기준 정렬의 추가 여부는 예제를 통해 정한다. “합쳐보기”라는 표현만으로 세 화면을 모두 구현하지 않는다.

변경 대상:

- src/pix/viewer/visual_case_adapters.py
- src/pix/viewer/visual_contracts.py, visual_serialization.py
- src/pix/viewer/assets/visualization.js, visualization.css
- tests/viewer/test_visualization_ui.cjs
- 새 browser 테스트와 해당 사용 가이드·예제

UI 제안:

1. 그룹별 variant 목록에 빈도·비율·누적 비율을 표시한다.
2. 상위 variant 개수 20%/80%/100%와 정수 직접 입력, 실제 variant 비중과 별도 case coverage를 표시한다.
3. 수동 체크로 희귀 variant를 추가·제외한다.
4. 선택 결과를 같은 화면의 그룹별 여러 행으로 본다. 현재 대표 비교는 별도 모드로 유지한다.
5. 긴 한글·반복 활동·원 case/event ID를 조회할 수 있게 한다.

정렬이 필요한 모드에서는 목록 전체의 모든 pair를 미리 정렬하지 않는다. 선택 집합과 명시 기준에 필요한 계산을 Python에서 수행하고 artifact를 재생성하는 경로부터 설계한다. 정적 HTML에서 선택만 바꿨는데 필요한 정렬 증거가 없다면 계산 필요 상태를 표시한다. 실행 서버나 브라우저 Python을 이 패치에 암묵적으로 추가하지 않는다.

저장 구분:

- 계산 JSON은 원 결과이며 화면 선택 때문에 수정하지 않는다.
- 선택 상태 export에는 source/계산 identity에 결합된 catalog_id, 그룹, variant IDs, 요청 variant 비중과 선택 case 수, 검색·그룹 표시 상태을 포함한다.
- SVG는 실제 선택 화면과 설명을 보존한다.
- 다시 열 때 source 또는 profile이 다르면 이전 선택을 조용히 다른 데이터에 적용하지 않는다.

수락 조건: 선택/해제·빈 선택·기준 변경·긴 한글·키보드 조작·작은 화면·SVG/선택 상태 복원이 동작한다. 렌더링 한도와 계산 한도를 구별한다. 동일 열의 삽입이나 그래프의 경로를 근거 없이 대응·원인 관계로 설명하지 않는다. 규모별 시간·메모리를 측정 전 수치로 약속하지 않는다.

### F03 브라우저 라벨 편집은 조건부

현재는 원 case 속성 또는 명시적 TraceGroup으로 그룹을 입력한다. 이 방법으로 업무가 가능하면 새 편집기를 만들지 않는다.

착수할 경우의 최소 요구: case 선택, 라벨 부여·변경·해제, 변경 취소, 변경 내역과 source identity 보존, 저장·재열기, 재계산 필요 표시. 현재 disjoint group 계약을 유지하고, 중복 라벨 그룹이 필요하면 별도 의미·분모 설계를 먼저 한다.

안전한 초기 저장안은 원 로그와 분리된 case ID→라벨 mapping이다. 저장만으로 이미 계산된 비교 결과를 갱신했다고 표시하지 않는다. 파일 형식과 source mismatch 처리의 예제를 만든 뒤 범위를 정한다.

## 5. 기존 검증 계획의 유지

아래 항목은 삭제하거나 완료 처리하지 않는다. Schumpeter가 실제 호출할 API부터 우선하고, 나머지는 기능 사용과 결함 발견에 따라 진행한다.

| 작업 | 구체적인 잔여 | 산출물과 종료 조건 |
| --- | --- | --- |
| V01 입력 의미 감사 | 기존 조사 범위 170개 중 기록상 150개 미검토. constraints·advanced filter·learning/stream cutoff 우선. OPERA arc annotation·flooding 정의·OCEL 2.1 판본 차이 별도 | 함수별 입력 사용·미사용·분모·cutoff·결과·반례 연결. 기존 충족/노출 필요/결함/신규 필요/차단 판정 |
| V02 OCPM 화면 의미 | count 단위, joint/object/flattened 구별, 관측 witness, 상태, projection receipt, 접근성, export | 손계산 fixture→결과→codec→브라우저→export의 의미 일치. 실제 결함만 제품 수정 |
| V03 한도·근사·sequence | exact OC variants, 근사 비용 범위·witness, n-gram 반복·순서, 규모별 비용 | 독립 기대값과 한도 반례. 근사 bound를 통계 신뢰구간으로 표현하지 않음 |
| V04 환경·CI·참조·출시 | 미실행 OS/Python/optional 경로, CI, 기능별 PM4Py/OCPA 대조, 독립 출시 | 실행한 조합만 증명. 참조판본과 지원 profile 고정. 출시 범위를 명시 |

V01의 150개는 새로 구현해야 할 함수 수가 아니다. 검토한 20개 역시 전체 정확성·참조 대체·사용자 수락이 완료됐다는 뜻은 아니다.

CI 제안은 좁은 범위부터 시작한다. 예를 들어 Linux Python 3.10의 core/wheel, Windows Python 3.13의 설치·핵심 smoke, Node UI를 구분하고 browser·optional imports는 별도 job으로 둔다. 정확한 matrix와 실행 비용은 구현 시 결정한다. 실제 job 동작 확인 후 필수 check 여부를 정하며 branch protection은 이 문서 작성이나 workflow 추가로 자동 변경하지 않는다.

기존 R01~R14의 입력·출력, 모델·발견·적합성, feature·학습, 조직, 시뮬레이션, stream, 제약·action·privacy, 시각화, Agent 경계 확장은 원 추적표를 유지한다. 이미 구현한 XES/CSV/Parquet 출력, 투영, n-gram, stream 등을 미구현으로 다시 세지 않는다.

## 6. 보류 항목과 다시 검토할 조건

### H01 대표 Trace 선정과 주요 공통 노드

현재 최빈·수동 대표를 유지한다. 새 기본 알고리즘, medoid, 공통 노드 기반 선정, 합거리/최대거리 목적의 multi-alignment는 이 계획에서 구현 완료나 확정 요구로 올리지 않는다.

다시 검토할 자료:

- 같은 주요 활동을 지나지만 중간 분기나 재작업이 다른 사례.
- 같은 활동명이 여러 번 나타나 어느 occurrence를 기준으로 삼느냐가 달라지는 사례.
- 빈도는 낮지만 업무상 중요한 실패 경로.
- 최빈 대표, 수동 대표, 공통 지점 기반 후보가 서로 다른 판단을 만드는 작은 사례.

주요 노드가 활동 라벨인지 특정 모델 노드인지 원 event occurrence인지 먼저 구별한다. OCEL 공유 이벤트·동시성·부분순서를 다룰 경우 case sequence의 공통 노드 규칙을 그대로 일반화하지 않는다.

판단 기준: 선택된 대표가 검토 목적에 필요한 경로 차이를 보존하는가. 중요한 분기·반복이 가려지거나 노드 매칭이 불명확하면 해당 선정 규칙을 채택하지 않고 현재 방식 또는 여러 Trace 집합 보기를 유지한다.

### H02 ILP discovery

공부와 공동 설계 전 착수 보류를 유지한다. 학습 자료·작은 region/제약 예제 준비와 실제 알고리즘 구현을 구별한다. Schumpeter 전환 때문에 ILP 보류를 해제하지 않는다.

## 7. 사용자 확인과 개발 담당 확인

| 담당 | 확인할 내용 | 시점 |
| --- | --- | --- |
| 개발 담당 | 입력 계약, 계산·identity·codec, 예제, 설치·브라우저·export, 실패 재현, 미검증 기록 | 패치마다 |
| minero 선생님 | 대표·차이가 업무상 중요한 내용을 드러내는지, 실제 조작이 편한지 | 사용하면서 |
| minero 선생님 | 복수 sequence 행 사용 후 추가 표현·라벨 편집 필요 판단 | 실사용 중; 20% 분모는 확정됨 |
| 공동 검토 | 새 대표 선정 목적과 공통 노드 정의, ILP 설계 | H01/H02 재개 시 |

판단을 요청할 때는 선택지 설명만 보내지 않고 같은 작은 입력에 대한 화면·기대 차이를 준비한다. 기술 검사나 이미 합의한 구현을 매번 사용자 승인 항목으로 돌리지 않는다. 미결정 의미가 없는 작업은 계속 진행한다.

## 8. 통합과 회귀 운영

- work는 사용자 요청대로 Work 작업 공간으로 유지한다. Local Codex와 같은 checkout에서 동시에 쓰지 않는다.
- 새 패치는 갱신된 기준에서 짧은 topic branch 또는 독립 worktree를 사용한다. 브랜치·기준 SHA·담당 파일·완료 조건을 시작 기록에 남긴다.
- 공통 viewer/codec 파일은 한 패치를 먼저 통합한 뒤 다음 패치를 갱신한다. 충돌 없는 merge를 의미적 호환성의 증명으로 보지 않는다.
- 문서만 바뀌면 링크·상태·기준을 검토한다. 계산 변경은 독립 기대값, codec 변경은 왕복·호환, UI 변경은 실제 해당 흐름을 검증한다.
- 전체 회귀는 공통 계약 변경이나 실제 통합 위험이 있을 때 수행한다. 낮은 영향의 문서 변경을 위해 구현을 복제하는 테스트를 추가하지 않는다.
- 실패·skip·미실행과 환경 차이를 기록한다. 기대값 완화나 skip 추가로 결함을 숨기지 않는다.
- 배포 후 결함은 최소 반례와 함께 수정하거나 해당 기능 커밋을 검토 가능한 revert로 되돌린다. 공용 브랜치 강제 push와 다른 작업의 변경 취소는 하지 않는다.
- 기존 공개 API와 artifact를 깨는 변경은 별도 version·migration·수락 사례를 준비한다.

## 9. Schumpeter로 전환하는 종료 기준

아래 다섯 항목이 만족되면 PIX의 최소 마무리 묶음을 닫는 것을 제안한다.

1. 사용할 PIX 기준 SHA와 설치 가능한 artifact가 고정돼 있다.
2. 대표 Trace 비교의 작은 예제가 계산·화면·내보내기까지 재현된다.
3. 실제 사용할 경로의 알려진 치명적 결함이 해결됐거나 해당 경로가 명확하게 제외돼 있다.
4. 사용자 도메인 수락 대기, 다른 환경 미검증, 참조 대조와 고급 확장이 후속 목록에 남아 있다.
5. Schumpeter 담당자가 입력·결과·identity·상태와 PIX의 책임 경계를 알고 시작할 수 있다.

이 종료는 PIX 전체 개발 완료, 독립 정식 출시, 전체 참조 대체 승인과 다르다. 전체 잔여 작업을 끝내지 않고 현재 기능을 그대로 사용하며 새 개발을 하지 않는 선택도 가능하다.

소요 기간·개발 공수·전체 완료율·대규모 처리량은 알 수 없음이다. 해당 수치는 작업과 측정 근거가 생길 때만 추가한다.

## 10. 근거와 계획 변경 조건

원격 파일과 코드를 2026년 10월 10일 확인했다. 위 main/work SHA, 현재 공개 계약, 이번 대화의 사용자 결정에 대해 유효하다.

다음 조건이면 영향을 받는 패치만 다시 검토한다.

- main/work 또는 공유 API·codec·profile 변경.
- 독립 반례에서 count·순서·identity·cutoff·결과 상태가 잘못됨을 확인.
- 실제 사용에서 대표·표시가 중요한 업무 차이를 가리거나 잘못된 결론을 유도.
- 확정한 variant 개수 비중 외의 선택 정책이 추가로 필요함.
- Schumpeter가 인계 범위 밖의 계산이나 상태 계약을 실제로 필요로 함.
- OCEL 등의 고정 표준 판본이 바뀌고 그 차이가 사용 경로에 영향을 줌.

기존 구현이 충분하다는 근거가 나오면 해당 신규 패치는 생략한다. 불확실성이 남는 항목은 “미확인”으로 유지하고 자동으로 미구현 또는 완료로 바꾸지 않는다.

### 저장소 근거

- [현재 main과 work 차이](https://github.com/Chanta-Research-Group/PIX/compare/2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3...b343a5bee613ec243848432c98a4e51843c9e17a)
- [통합 실행 인덱스](https://github.com/Chanta-Research-Group/PIX/blob/2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3/docs/requirements/2026-10-06_PIX_INTEGRATED_EXECUTION_PLAN.md)
- [NEXT 00부터 05까지의 실행계획](https://github.com/Chanta-Research-Group/PIX/blob/2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3/docs/requirements/2026-10-04_PIX_PARALLEL_DEVELOPMENT_PLAN.md)
- [입력 의미 감사](https://github.com/Chanta-Research-Group/PIX/blob/2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3/docs/reports/2026-10-06_PIX_OCPM_INPUT_AUDIT.md)
- [대표 Trace 비교 구현 보고서](https://github.com/Chanta-Research-Group/PIX/blob/b343a5bee613ec243848432c98a4e51843c9e17a/docs/reports/2026-10-07_PIX_TRACE_GROUP_COMPARISON.md)
- [대표 Trace 비교 사용 가이드](https://github.com/Chanta-Research-Group/PIX/blob/b343a5bee613ec243848432c98a4e51843c9e17a/docs/user-guide/TRACE_GROUP_COMPARISON_GUIDE.md)
- [비교 계산 코드](https://github.com/Chanta-Research-Group/PIX/blob/b343a5bee613ec243848432c98a4e51843c9e17a/src/pix/case_centric/trace_comparison.py)
- [OC 구조 variant 계산 코드](https://github.com/Chanta-Research-Group/PIX/blob/b343a5bee613ec243848432c98a4e51843c9e17a/src/pix/compute/variants.py)
- [패키징 선언](https://github.com/Chanta-Research-Group/PIX/blob/b343a5bee613ec243848432c98a4e51843c9e17a/pyproject.toml)
- [기존 R01부터 R14까지의 잔여 설계](https://github.com/Chanta-Research-Group/PIX/blob/b343a5bee613ec243848432c98a4e51843c9e17a/docs/requirements/2026-09-18_PIX_RESIDUAL_DETAILED_DESIGN.md)

프로젝트 첨부 문서 PIX_PROJECT_CONTEXT_AND_ARCHITECTURE.md의 2026년 7월 18일 초기 아키텍처도 책임 분리 확인에 사용했다. 구현 완료 상태는 위 최신 코드·보고서를 기준으로 판단했다.

