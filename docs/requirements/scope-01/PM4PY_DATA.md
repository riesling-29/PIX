# SCOPE-01 세부 대체표 — PM4Py 데이터·OCEL·입출력

기준일: **2026-09-14**. [전체 범례·증거·판정 경계](../2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md).
입력·출력은 대체할 기능을 검토하기 위한 계약이다. **현재 PIX가 이미 그 결과를 반환한다는 뜻은 아니다.** 현재 지원은 각 행의 구현·의미·소스·증거로 구분한다.
참조 경로와 symbol은 공식 배포 wheel의 위치다. wrapper·helper·backend는 추적을 위해 함께 표시하며 별도 계산 알고리즘으로 중복 집계하지 않는다.

| ID | 도메인에서 판단할 질문 | PIX 구현 | 의미 대응 | 다음 작업 |
|---|---|---|---|---|
| [PM-DATA-001](#pm-data-001) | Case별 최초·마지막 활동과 그 빈도는 무엇인가? | 부분 대응 | 일부 의미 겹침 | IO-02, STAT-01 |
| [PM-DATA-002](#pm-data-002) | 이벤트·case에서 어떤 속성이 관측되고 값이 얼마나 나타나는가? | 부분 대응 | 일부 의미 겹침 | STAT-01, STAT-02 |
| [PM-DATA-003](#pm-data-003) | 동일 활동열의 case들은 무엇이며 variant 빈도·coverage는 얼마인가? | 대응 구현 없음 | 미구현 | IO-02, STAT-01 |
| [PM-DATA-004](#pm-data-004) | 각 variant의 반복 경로별 소요시간 분포는 어떠한가? | 대응 구현 없음 | 미구현 | STAT-03, PERF-01, PERF-04 |
| [PM-DATA-005](#pm-data-005) | 관측 로그 또는 모델의 trace 확률 언어는 무엇인가? | 대응 구현 없음 | 미구현 | STAT-01, FEAT-04, SIM-01 |
| [PM-DATA-006](#pm-data-006) | 같은 활동이 다시 나타날 때 최소 몇 개 활동을 거치고 어떤 활동이 사이에 있는가? | 대응 구현 없음 | 미구현 | STAT-02, DISC-06 |
| [PM-DATA-007](#pm-data-007) | Case의 평균 도착 간격과 종료 간격은 얼마인가? | 대응 구현 없음 | 미구현 | STAT-03, PERF-04, PERF-05 |
| [PM-DATA-008](#pm-data-008) | 활동별로 재작업한 case 수와 반복 이벤트 수는 얼마인가? | 대응 구현 없음 | 미구현 | STAT-02 |
| [PM-DATA-009](#pm-data-009) | 동시에 진행되는 case 또는 실행 구간은 몇 개인가? | 대응 구현 없음 | 미구현 | STAT-03, PERF-04, ORG-03 |
| [PM-DATA-010](#pm-data-010) | 겹치는 구간을 고려한 cycle time은 얼마인가? | 대응 구현 없음 | 미구현 | STAT-03, PERF-04 |
| [PM-DATA-011](#pm-data-011) | 실제 시작·완료가 기록된 활동의 service time은 얼마인가? | 부분 대응 | 일부 의미 겹침 | IO-03, PERF-01, PERF-04, PERF-05 |
| [PM-DATA-012](#pm-data-012) | Case 전체와 개별 case의 기간 분포는 어떠한가? | 대응 구현 없음 | 미구현 | STAT-03, PERF-04, PERF-05 |
| [PM-DATA-013](#pm-data-013) | 자주 등장하는 부분 활동열은 무엇인가? | 대응 구현 없음 | 미구현 | STAT-02, FEAT-02 |
| [PM-DATA-014](#pm-data-014) | 활동이 case의 몇 번째 위치에서 발생하는가? | 대응 구현 없음 | 미구현 | STAT-02 |
| [PM-DATA-015](#pm-data-015) | 두 속성 축으로 나눈 process cube의 집계 결과는 무엇인가? | 대응 구현 없음 | 미구현 | STAT-01, STAT-02, FILTER-01 |
| [PM-DATA-016](#pm-data-016) | 주어진 활동 전후에 얼마의 시간이 걸리는가? | 대응 구현 없음 | 미구현 | PERF-01, PERF-04 |
| [PM-DATA-017](#pm-data-017) | 활동 실행 구간의 겹침으로 본 concurrent 활동쌍은 무엇인가? | 대응 구현 없음 | 미구현 | IO-03, STAT-03, PERF-04 |
| [PM-DATA-018](#pm-data-018) | 활동쌍의 eventually-follows 빈도는 얼마인가? | 대응 구현 없음 | 미구현 | STAT-02, DISC-06 |
| [PM-DATA-019](#pm-data-019) | 숫자 속성·기간의 연속 분포와 시간 단위별 빈도는 어떠한가? | 대응 구현 없음 | 미구현 | STAT-02, STAT-03 |
| [PM-DATA-020](#pm-data-020) | 여러 활동을 통과하는 시간 경로의 performance spectrum은 어떠한가? | 대응 구현 없음 | 미구현 | PERF-01, PERF-04 |
| [PM-DATA-021](#pm-data-021) | 관측 순서가 복잡하고 불규칙한 활동을 어떻게 찾는가? | 대응 구현 없음 | 미구현 | STAT-02, DISC-06 |
| [PM-DATA-022](#pm-data-022) | 원하는 시작·종료 활동의 case만 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [PM-DATA-023](#pm-data-023) | 이벤트·case 속성 값과 출현 비율에 따라 로그를 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [PM-DATA-024](#pm-data-024) | 어떤 variant를 남기고 빈도·coverage를 어떻게 제한하는가? | 대응 구현 없음 | 미구현 | FILTER-01, STAT-01, FILTER-03 |
| [PM-DATA-025](#pm-data-025) | 직접 또는 나중에 이어지는 특정 활동 관계를 가진 case를 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [PM-DATA-026](#pm-data-026) | 시간창에 포함·교차·시작·종료하는 case 또는 event를 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03, PERF-01 |
| [PM-DATA-027](#pm-data-027) | 두 활동 사이·prefix·suffix·지정 부분열을 추출할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03 |
| [PM-DATA-028](#pm-data-028) | 길이·기간·재작업 횟수로 case를 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, STAT-02, PERF-04 |
| [PM-DATA-029](#pm-data-029) | 특정 경로에 너무 오래 걸리는 case를 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, PERF-01, FILTER-03 |
| [PM-DATA-030](#pm-data-030) | 동일 활동을 서로 다른 사람이 처리하거나 업무 분리가 지켜지는가? | 대응 구현 없음 | 미구현 | FILTER-01, ORG-01 |
| [PM-DATA-031](#pm-data-031) | 연속·동률 이벤트를 묶거나 활동 발생을 기준으로 case를 분할할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03, IO-02 |
| [PM-DATA-032](#pm-data-032) | DFG의 잦은 활동·경로와 특정 활동 주변 연결만 남길 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-03, MODEL-06 |
| [PM-DATA-033](#pm-data-033) | EventLog·stream·표 형식을 의미 손실을 드러내며 오갈 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-02, IO-05, FILTER-03 |
| [PM-DATA-034](#pm-data-034) | Case 로그의 이벤트·자원 관계를 graph로 볼 수 있는가? | 대응 구현 없음 | 미구현 | REL-01, FILTER-03 |
| [PM-DATA-035](#pm-data-035) | Case의 인접 이벤트 사이 시간 구간을 추출할 수 있는가? | 대응 구현 없음 | 미구현 | IO-03, PERF-01 |
| [PM-DATA-036](#pm-data-036) | Lifecycle 이벤트를 실행 interval로 짝짓고 다시 lifecycle로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | IO-03, PERF-01, PERF-04, PERF-05 |
| [PM-OCEL-001](#pm-ocel-001) | 객체형·속성 목록과 활동별 객체 참여 개수는 무엇인가? | 부분 대응 | 일부 의미 겹침 | STAT-01, STAT-02, REL-01 |
| [PM-OCEL-002](#pm-ocel-002) | 동일 시각에 일어난 활동과 참여 객체들은 무엇인가? | 대응 구현 없음 | 미구현 | STAT-01, STAT-03 |
| [PM-OCEL-003](#pm-ocel-003) | 객체별 관측 활동열·기간·상호작용 객체는 무엇인가? | 부분 대응 | 일부 의미 겹침 | STAT-01, PERF-04, REL-01 |
| [PM-OCEL-004](#pm-ocel-004) | 하나의 객체형을 case로 삼아 OCEL을 펼칠 수 있는가? | 부분 대응 | 일부 의미 겹침 | IO-02, OCEXEC-02, FILTER-03 |
| [PM-OCEL-005](#pm-ocel-005) | 객체형마다 어떤 활동이 직접 이어지고 각 수치는 무엇을 세는가? | 부분 대응 | PIX 자체 정의 | STAT-01, PERF-01, PERF-05, OCEXEC-02 |
| [PM-OCEL-006](#pm-ocel-006) | 객체형별 net을 결합한 OCPN을 발견할 수 있는가? | 부분 대응 | PIX 자체 정의 | DISC-01, DISC-02, MODEL-01 |
| [PM-OCEL-007](#pm-ocel-007) | 공동 참여·후속·계승·동시 최초/최종 관측 관계를 graph로 만들 수 있는가? | 대응 구현 없음 | 미구현 | REL-01, OCEXEC-02 |
| [PM-OCEL-008](#pm-ocel-008) | 관측에서 유도한 객체 관계를 O2O에 추가할 수 있는가? | 부분 대응 | 일부 의미 겹침 | REL-01, FILTER-03 |
| [PM-OCEL-009](#pm-ocel-009) | 객체의 최초·최종 참여를 E2O lifecycle qualifier로 표시할 수 있는가? | 대응 구현 없음 | 미구현 | REL-01, REL-03, OCEXEC-02 |
| [PM-OCEL-010](#pm-ocel-010) | Event·object·connected component 단위로 OCEL을 표본 추출할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, FILTER-03, OCEXEC-04 |
| [PM-OCEL-011](#pm-ocel-011) | 동일 관측을 중복 제거하거나 event를 병합할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, FILTER-03 |
| [PM-OCEL-012](#pm-ocel-012) | 동률 이벤트를 추가 속성으로 정렬하거나 명시적 순서로 처리할 수 있는가? | 부분 대응 | PIX 자체 정의 | OCEXEC-02, FILTER-03 |
| [PM-OCEL-013](#pm-ocel-013) | 서로 연결된 객체들 또는 중심 객체의 관련 실행으로 OCEL을 나눌 수 있는가? | 부분 대응 | PIX 자체 정의 | OCEXEC-01, OCEXEC-04, FILTER-02 |
| [PM-OCEL-014](#pm-ocel-014) | 중심 객체 실행들이 동일한 구조인지 묶어서 설명할 수 있는가? | 부분 대응 | PIX 자체 정의 | OCEXEC-03, FEAT-03 |
| [PM-OCEL-015](#pm-ocel-015) | 객체 속성 값으로 타입을 세분화하거나 다시 묶을 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-02, FILTER-03, REL-02 |
| [PM-OCEL-016](#pm-ocel-016) | 객체 참여 정보를 event 타입에 펼쳤다가 되돌릴 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-02, FILTER-03, REL-01 |
| [PM-OCEL-017](#pm-ocel-017) | 이벤트·객체의 속성 조건과 시간 범위로 OCEL을 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, FILTER-03, REL-02 |
| [PM-OCEL-018](#pm-ocel-018) | 객체형·객체 ID·event ID를 선택하고 연결 범위를 조절할 수 있는가? | 부분 대응 | 일부 의미 겹침 | FILTER-01, FILTER-02, FILTER-03 |
| [PM-OCEL-019](#pm-ocel-019) | 활동과 객체형 조합·참여 개수·형별 시작/종료 이벤트를 필터링할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, STAT-01, OCEXEC-02 |
| [PM-OCEL-020](#pm-ocel-020) | 특정 객체·크기·타입·활동이 있는 connected component만 선택할 수 있는가? | 대응 구현 없음 | 미구현 | FILTER-01, FILTER-02, OCEXEC-01 |
| [PM-OCEL-021](#pm-ocel-021) | 활동형–객체형 참여 graph와 빈도는 무엇인가? | 대응 구현 없음 | 미구현 | STAT-01, REL-01, DISC-06 |
| [PM-OCEL-022](#pm-ocel-022) | 객체 관계를 객체형 수준으로 묶은 OTG는 무엇인가? | 대응 구현 없음 | 미구현 | REL-01, DISC-06 |
| [PM-OCEL-023](#pm-ocel-023) | 실제 OCDFG와 기준 OCDFG의 활동·경로·빈도 차이는 무엇인가? | 대응 구현 없음 | 미구현 | SCOPE-01, DISC-06, STAT-01, REL-03 |
| [PM-OCEL-024](#pm-ocel-024) | 실제 ET-OT·OTG와 기준 graph의 관계·빈도 차이는 무엇인가? | 대응 구현 없음 | 미구현 | SCOPE-01, REL-01, REL-03, STAT-01 |
| [PM-OCEL-025](#pm-ocel-025) | 객체 결합의 arc-weight 분포를 가진 SAW net을 발견할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-01, MODEL-02, SIM-02 |
| [PM-OCEL-026](#pm-ocel-026) | 연관된 두 case 로그의 교차 행동과 연결 사슬을 발견할 수 있는가? | 대응 구현 없음 | 미구현 | REL-01, OCEXEC-02, IO-05 |
| [PM-OCEL-027](#pm-ocel-027) | 객체별 활동열·관계 graph·속성·work-in-progress를 feature로 만들 수 있는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, REL-02 |
| [PM-OCEL-028](#pm-ocel-028) | 이벤트의 시각·활동·참여 객체와 신규 관계를 feature로 만들 수 있는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, REL-01 |
| [PM-OCEL-029](#pm-ocel-029) | 각 event–object 참여 시점까지의 prefix feature를 만들 수 있는가? | 대응 구현 없음 | 미구현 | FEAT-01, FEAT-02, OCEXEC-02 |
| [PM-OCEL-030](#pm-ocel-030) | Case·표 자료를 복수 객체형을 갖는 OCEL로 변환할 수 있는가? | 부분 대응 | PIX 자체 정의 | IO-05, FILTER-03 |
| [PM-OCEL-031](#pm-ocel-031) | OCEL의 event/object/직접후속 또는 object feature 관계를 graph로 변환할 수 있는가? | 대응 구현 없음 | 미구현 | REL-01, FEAT-02, FILTER-03 |
| [PM-OCEL-032](#pm-ocel-032) | 속성을 객체로 승격하거나 object-event 관계를 explode하고 부모–자식 참조를 만들 수 있는가? | 대응 구현 없음 | 미구현 | REL-01, FILTER-02, FILTER-03 |
| [PM-OCEL-033](#pm-ocel-033) | OCEL의 관계 multiplicity 때문에 flattening에 convergence/divergence가 생기는가? | 대응 구현 없음 | 미구현 | STAT-01, REL-01, IO-02 |
| [PM-OCEL-034](#pm-ocel-034) | 시점별 객체 상태·qualifier를 보존하고 조회 가능한 형식으로 전달할 수 있는가? | 부분 대응 | PIX 자체 정의 | REL-01, REL-02, REL-03, FILTER-02 |
| [PM-IO-001](#pm-io-001) | XES와 gzip XES를 case·기록 순서·classifier·중첩 속성을 보존하여 읽는가? | 구현 있음 | PIX 자체 정의 | IO-01, IO-02, IO-05 |
| [PM-IO-002](#pm-io-002) | CaseLog를 XES로 내보내 다른 분석 도구에 전달할 수 있는가? | 대응 구현 없음 | 미구현 | IO-04, IO-05 |
| [PM-IO-003](#pm-io-003) | 기본 OCEL 1 JSON을 객체·이벤트 손실을 설명하며 읽는가? | 부분 대응 | 일부 의미 겹침 | IO-01, IO-05 |
| [PM-IO-004](#pm-io-004) | OCEL 1 XML에서 이벤트·객체·속성 타입을 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05 |
| [PM-IO-005](#pm-io-005) | PM4Py classic 3-table SQLite 로그를 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05 |
| [PM-IO-006](#pm-io-006) | PM4Py의 기존 extended-table CSV와 선택적 객체 CSV를 가져오는가? | 부분 대응 | 일부 의미 겹침 | IO-01, IO-05 |
| [PM-IO-007](#pm-io-007) | 표준 OCEL 2 JSON의 타입·qualifier·O2O·속성 이력을 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05 |
| [PM-IO-008](#pm-io-008) | OCEL 2 XML의 타입·관계·시점별 속성을 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05 |
| [PM-IO-009](#pm-io-009) | OCEL 2 SQLite 타입별 테이블·관계·속성 이력을 읽는가? | 구현 있음 | 명시한 좁은 범위 대응 | IO-01, IO-05 |
| [PM-IO-010](#pm-io-010) | Compact OCEL CSV의 객체 참조·qualifier·속성 이력을 읽는가? | 구현 있음 | PIX 자체 정의 | IO-01, IO-05 |
| [PM-IO-011](#pm-io-011) | CSV/Parquet OCEL bundle을 디렉터리 또는 ZIP에서 읽는가? | 구현 있음 | PIX 자체 정의 | IO-01, IO-05 |
| [PM-IO-012](#pm-io-012) | Canonical 객체 로그를 OCEL 2 JSON/XML/SQLite로 보존하여 내보내는가? | 구현 있음 | PIX 자체 정의 | IO-01, IO-04, IO-05 |
| [PM-IO-013](#pm-io-013) | 기존 OCEL 1/PM4Py enriched JSON·XML·CSV·classic SQLite로 내보내는가? | 대응 구현 없음 | 미구현 | IO-04, IO-05 |
| [PM-IO-014](#pm-io-014) | Compact CSV와 CSV/Parquet bundle을 다른 도구에 내보내는가? | 대응 구현 없음 | 미구현 | IO-04, IO-05 |
| [PM-IO-015](#pm-io-015) | PNML 모델/구조 파일을 읽고 다시 내보내는가? | 대응 구현 없음 | 미구현 | MODEL-03, IO-05 |
| [PM-IO-016](#pm-io-016) | PTML 모델/구조 파일을 읽고 다시 내보내는가? | 대응 구현 없음 | 미구현 | MODEL-03, IO-05 |
| [PM-IO-017](#pm-io-017) | DFG 모델/구조 파일을 읽고 다시 내보내는가? | 대응 구현 없음 | 미구현 | MODEL-03, IO-05 |
| [PM-IO-018](#pm-io-018) | BPMN 모델/구조 파일을 읽고 다시 내보내는가? | 대응 구현 없음 | 미구현 | MODEL-03, IO-05 |
| [PM-IO-019](#pm-io-019) | HTTP/HTTPS 로그 주소를 입력하여 출처와 원본 파일을 확보한 뒤 읽는가? | 대응 구현 없음 | 미구현 | IO-05 |
| [PM-DATA-037](#pm-data-037) | 분석용 가상 시작·종료 이벤트를 명시적으로 추가할 수 있는가? | 대응 구현 없음 | 미구현 | IO-02, FILTER-03 |
| [PM-DATA-038](#pm-data-038) | Case 전체의 service·sojourn·waiting을 집계하여 붙일 수 있는가? | 대응 구현 없음 | 미구현 | IO-03, PERF-01, PERF-04, PERF-05 |
| [PM-DATA-039](#pm-data-039) | 동일 활동 라벨을 전후 문맥에 따라 구분할 수 있는가? | 대응 구현 없음 | 미구현 | STAT-02, FEAT-03, FILTER-03 |
| [PM-DATA-040](#pm-data-040) | 서로 연관된 case 관계표를 사용해 두 로그를 결합할 수 있는가? | 대응 구현 없음 | 미구현 | IO-05, REL-01, FILTER-03 |
| [PM-DATA-041](#pm-data-041) | 활동열의 공통 prefix를 trie 구조로 표현할 수 있는가? | 대응 구현 없음 | 미구현 | DISC-06, MODEL-02, STAT-01 |

## PM-DATA-001

**Case별 최초·마지막 활동과 그 빈도는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | CaseLog/TraceSet, activity classifier와 기록 순서, 빈 case 포함 정책. |
| 확인할 출력 | 시작·종료 활동별 case 빈도와 빈 case 수. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | CaseLog/TraceSet의 source order와 classifier를 직접 받는 경계 통계 연결; 빈 case 분모. |
| 다음 작업 ID | IO-02, STAT-01 |
| 의미·옵션·한계 | PIX DFG에 객체형별 starts/ends가 있으나 공개 discover_dfg는 OCEL 경로. XES source-order를 시각 정렬로 치환하면 동일 계산이 아니다. |

**현재 PIX 근거:** `discover_dfg`, `case_traces`.
소스: [src/pix/compute/dfg.py](../../../src/pix/compute/dfg.py), [src/pix/event_log/adapters.py](../../../src/pix/event_log/adapters.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_start_activities`
- `pm4py/stats.py :: get_end_activities`

## PM-DATA-002

**이벤트·case에서 어떤 속성이 관측되고 값이 얼마나 나타나는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 이벤트·case 속성과 scope, 값 타입, per-case 중복 집계 정책. |
| 확인할 출력 | 속성 이름·값별 빈도·누락률과 집계 모집단. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 속성명/값별 빈도, missing, unique/per-case 빈도 연산과 evidence 반환. |
| 다음 작업 ID | STAT-01, STAT-02 |
| 의미·옵션·한계 | PIX는 속성 보존과 OCEL 구조별 개수를 제공하지만 임의 event/case 속성 분포 연산은 없다. |

**현재 PIX 근거:** `OCEL.info`, `CaseLog.attribute`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py), [src/pix/event_log/model.py](../../../src/pix/event_log/model.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_event_attributes`
- `pm4py/stats.py :: get_trace_attributes`
- `pm4py/stats.py :: get_event_attribute_values`
- `pm4py/stats.py :: get_trace_attribute_values`

## PM-DATA-003

**동일 활동열의 case들은 무엇이며 variant 빈도·coverage는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 정렬된 활동열, classifier와 선택 case 집합. |
| 확인할 출력 | 활동열 variant별 case ID·빈도·coverage 및 분할 로그. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case 활동열 tuple 동치, 빈 trace, classifier 기준 grouping/빈도/분할을 공개 연산으로 제공. |
| 다음 작업 ID | IO-02, STAT-01 |
| 의미·옵션·한계 | get_variants는 get_variants_as_tuples로 위임하는 facade. PIX incidence graph variant는 이 case activity-sequence variant와 다른 정의이므로 구현으로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_variants`
- `pm4py/stats.py :: get_variants_as_tuples`
- `pm4py/stats.py :: split_by_process_variant`

## PM-DATA-004

**각 variant의 반복 경로별 소요시간 분포는 어떠한가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case variant와 각 event의 start/complete, 반복 경로 위치. |
| 확인할 출력 | Variant·path occurrence별 기간 표본과 집계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Variant별 path occurrence-index와 start/complete 시각을 연결한 duration summary. |
| 다음 작업 ID | STAT-03, PERF-01, PERF-04 |
| 의미·옵션·한계 | 활동쌍만 같아도 반복 위치가 다른 path를 합칠지 구분한다. 현재 객체 DFG gap 집계만으로 대체되지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_variants_paths_duration`

## PM-DATA-005

**관측 로그 또는 모델의 trace 확률 언어는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 관측 case log 또는 PN/tree/DFG 모델과 playout 설정. |
| 확인할 출력 | Trace별 확률과 근사·미관측·절단 질량 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 로그의 정규화 variant 분포와 모델 playout 기반 근사 언어를 분리 구현. |
| 다음 작업 ID | STAT-01, FEAT-04, SIM-01 |
| 의미·옵션·한계 | Log/DataFrame/ProcessTree/PN/DFG 입력에서 계산 경로가 다르다. 모델 playout은 잘린 확률 질량과 seed/한도를 명시해야 한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_stochastic_language`

## PM-DATA-006

**같은 활동이 다시 나타날 때 최소 몇 개 활동을 거치고 어떤 활동이 사이에 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 기록 순서가 있는 활동열과 activity key. |
| 확인할 출력 | 활동별 최소 재발 거리와 그 사이의 witness 활동 집합. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 최소 self distance와 witness 활동 집합; 재발 없음/즉시 반복/중복 witness 경계 검산. |
| 다음 작업 ID | STAT-02, DISC-06 |
| 의미·옵션·한계 | LOG/PANDAS/POLARS는 backend이고 POLARS는 가용성에 따라 fallback한다. 경과시간 거리가 아니라 사이에 낀 이벤트 수 정의. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_minimum_self_distances`
- `pm4py/stats.py :: get_minimum_self_distance_witnesses`
- `pm4py/algo/discovery/minimum_self_distance/algorithm.py :: apply`
- `pm4py/discovery.py :: derive_minimum_self_distance`
- 변형 `pm4py/algo/discovery/minimum_self_distance/algorithm.py :: Variants` → `LOG`, `PANDAS`, `POLARS`

## PM-DATA-007

**Case의 평균 도착 간격과 종료 간격은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 최초·최종 event 시각과 calendar 정책. |
| 확인할 출력 | Case 도착·종료 간격의 표본 수와 평균. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case별 start/end 산출과 arrival/dispersion 집계; timezone/business calendar·미완료 분모. |
| 다음 작업 ID | STAT-03, PERF-04, PERF-05 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_case_arrival_average`
- `pm4py/statistics/traces/generic/log/case_arrival.py :: get_case_arrival_avg`
- `pm4py/statistics/traces/generic/log/case_arrival.py :: get_case_dispersion_avg`
- `pm4py/analysis.py :: insert_case_arrival_finish_rate`

## PM-DATA-008

**활동별로 재작업한 case 수와 반복 이벤트 수는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 활동열과 재작업 횟수 정의. |
| 확인할 출력 | 활동별 재작업 case 수·비율 또는 반복 occurrence 수. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 재작업 case 비율과 반복 occurrence 횟수를 별도 집계. |
| 다음 작업 ID | STAT-02 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_rework_cases_per_activity`
- `pm4py/statistics/rework/log/get.py :: apply`

## PM-DATA-009

**동시에 진행되는 case 또는 실행 구간은 몇 개인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case span 또는 start/complete interval들과 경계 포함 정책. |
| 확인할 출력 | 각 구간의 overlap 수와 겹치는 구간 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case span/interval overlap 집계와 경계 포함 정의; zero-length·동률·결측 처리. |
| 다음 작업 ID | STAT-03, PERF-04, ORG-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_case_overlap`
- `pm4py/statistics/overlap/interval_events/log/get.py :: apply`

## PM-DATA-010

**겹치는 구간을 고려한 cycle time은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 실행 구간과 case 수, cycle-time 정의. |
| 확인할 출력 | 구간 union 기반 cycle time과 계산 분자·분모. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 관측 구간의 union과 instance 수에 따른 cycle time 정의를 구현; elapsed case duration과 구분. |
| 다음 작업 ID | STAT-03, PERF-04 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_cycle_time`

## PM-DATA-011

**실제 시작·완료가 기록된 활동의 service time은 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동별 명시 start·complete와 aggregation/calendar 설정. |
| 확인할 출력 | Service time 표본·집계·미측정 coverage. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | CaseLog interval 경로와 median/sum/min/max 등 aggregation 및 business calendar 연결. |
| 다음 작업 ID | IO-03, PERF-01, PERF-04, PERF-05 |
| 의미·옵션·한계 | PIX는 explicit datetime start_attribute와 event completion의 차이, unique event 표본 및 coverage를 제공한다. PM4Py statistics/sojourn_time/__init__.py는 service_time wildcard alias이므로 별도 sojourn 알고리즘으로 세지 않는다. |

**현재 PIX 근거:** `measure_temporal`.
소스: [src/pix/compute/temporal.py](../../../src/pix/compute/temporal.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_service_time`

## PM-DATA-012

**Case 전체와 개별 case의 기간 분포는 어떠한가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 event 시각, 선택 case ID와 calendar. |
| 확인할 출력 | 전체·개별 case duration과 분포·미완료 표식. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case source-order와 관측시각 span 정의, duration 목록/분위수/업무시간/미완료 처리. |
| 다음 작업 ID | STAT-03, PERF-04, PERF-05 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_all_case_durations`
- `pm4py/stats.py :: get_case_duration`

## PM-DATA-013

**자주 등장하는 부분 활동열은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 최소 지원도, subsequence 의미. |
| 확인할 출력 | 빈발 부분열과 case 지원도·매칭 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | PrefixSpan 기반 빈발 subsequence와 최소 지원도, wildcard 표현, 연속/비연속 구별. |
| 다음 작업 ID | STAT-02, FEAT-02 |
| 의미·옵션·한계 | 전체 variant나 directly-follows 통계와 다른 빈발 부분열 문제. 임계값 모집단은 case 기반인지 occurrence 기반인지 고정. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_frequent_trace_segments`

## PM-DATA-014

**활동이 case의 몇 번째 위치에서 발생하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 source-order 활동열. |
| 확인할 출력 | 활동별 0/1 기반 위치와 빈도 분포. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동의 위치 분포와 반복 occurrences, empty case, source-order 검산. |
| 다음 작업 ID | STAT-02 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_activity_position_summary`

## PM-DATA-015

**두 속성 축으로 나눈 process cube의 집계 결과는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case/event 표와 X/Y 속성, bin 경계, 집계 함수. |
| 확인할 출력 | 셀별 모집단·집계값을 가진 process cube. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 범주·수치 bin 경계와 셀별 aggregation의 모집단·분모 계약. |
| 다음 작업 ID | STAT-01, STAT-02, FILTER-01 |
| 의미·옵션·한계 | statistics/process_cube/algorithm.py는 pandas.algorithm wildcard alias. 임의 aggregation callable과 backend를 별도 계산 family로 부풀리지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/stats.py :: get_process_cube`
- `pm4py/statistics/process_cube/pandas/algorithm.py :: apply`
- `pm4py/statistics/process_cube/polars/algorithm.py :: apply`
- 변형 `pm4py/statistics/process_cube/pandas/algorithm.py :: Variants` → `CLASSIC`
- 변형 `pm4py/statistics/process_cube/polars/algorithm.py :: Variants` → `CLASSIC`

## PM-DATA-016

**주어진 활동 전후에 얼마의 시간이 걸리는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 선택 활동과 인접 경로의 event 시각, PRE/POST/PREPOST. |
| 확인할 출력 | 활동 전후 경로별 시간과 가중 집계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동별 incoming/outgoing path별 시간과 가중 평균; 관측 gap과 실제 waiting 구분. |
| 다음 작업 ID | PERF-01, PERF-04 |
| 의미·옵션·한계 | PRE/POST/PREPOST는 측정 방향 variant이고 backend가 아니다. PIX gap 원시는 재사용 가능하지만 해당 활동 중심 연산은 미구현. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/statistics/passed_time/log/algorithm.py :: apply`
- `pm4py/statistics/passed_time/pandas/algorithm.py :: apply`
- `pm4py/statistics/passed_time/polars/algorithm.py :: apply`
- 변형 `pm4py/statistics/passed_time/log/algorithm.py :: Variants` → `PRE`, `POST`, `PREPOST`
- 변형 `pm4py/statistics/passed_time/pandas/algorithm.py :: Variants` → `PRE`, `POST`, `PREPOST`
- 변형 `pm4py/statistics/passed_time/polars/algorithm.py :: Variants` → `PRE`, `POST`, `PREPOST`

## PM-DATA-017

**활동 실행 구간의 겹침으로 본 concurrent 활동쌍은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 실행 interval과 strict overlap 정책. |
| 확인할 출력 | 동시 활동쌍별 겹침 빈도와 대상 interval. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Interval overlap에 따른 활동쌍 횟수; strict/non-strict와 lifecycle pairing 검산. |
| 다음 작업 ID | IO-03, STAT-03, PERF-04 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/statistics/concurrent_activities/log/get.py :: apply`

## PM-DATA-018

**활동쌍의 eventually-follows 빈도는 얼마인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 first/all occurrence 계산 정책. |
| 확인할 출력 | Eventually-follows 활동쌍 빈도와 occurrence 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 직접/비직접 후속과 재발 pair multiplicity, keep-first 등 집계 의미. |
| 다음 작업 ID | STAT-02, DISC-06 |
| 의미·옵션·한계 | DFG는 인접 관계이며 eventually-follows를 대체하지 않는다. 유한 전체 순서/부분순서 profile을 구분. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/statistics/eventually_follows/log/get.py :: apply`
- `pm4py/discovery.py :: discover_eventually_follows_graph`

## PM-DATA-019

**숫자 속성·기간의 연속 분포와 시간 단위별 빈도는 어떠한가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 수치/시각 속성 표본과 bin·bandwidth·샘플링 설정. |
| 확인할 출력 | 빈도 분포 또는 KDE 추정 좌표와 설정. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 수치 KDE·날짜/요일/월 bin 통계 및 case duration KDE; bandwidth/sample/단위/추정임을 명시. |
| 다음 작업 ID | STAT-02, STAT-03 |
| 의미·옵션·한계 | 통계 모듈의 KDE와 JSON 직렬화 wrapper는 같은 계산을 공유한다. 커널 추정 그래프와 원시 빈도는 구분. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/statistics/attributes/common/get.py :: get_kde_numeric_attribute`
- `pm4py/statistics/attributes/common/get.py :: get_kde_numeric_attribute_json`
- `pm4py/statistics/attributes/log/get.py :: get_events_distribution`

## PM-DATA-020

**여러 활동을 통과하는 시간 경로의 performance spectrum은 어떠한가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 지정 활동열과 event 시각, connected/disconnected 및 sample 한도. |
| 확인할 출력 | Performance-spectrum 시간 좌표들의 집합과 표본 범위. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 연속/비연속 spectrum point 추출, sample 한도와 시간 순서·근거. |
| 다음 작업 ID | PERF-01, PERF-04 |
| 의미·옵션·한계 | LAZYFRAME 및 LAZYFRAME_DISCONNECTED는 polars import 가능 시 Variants 속성에 동적으로 추가되는 backend selector. 정적 Enum 멤버 4개와 분리해 기록하며 설치/실행해 검증한 것은 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/performance_spectrum/algorithm.py :: apply`
- `pm4py/algo/discovery/performance_spectrum/algorithm.py :: is_polars_lazyframe`
- 변형 `pm4py/algo/discovery/performance_spectrum/algorithm.py :: Variants` → `DATAFRAME`, `LOG`, `DATAFRAME_DISCONNECTED`, `LOG_DISCONNECTED`, `LAZYFRAME`, `LAZYFRAME_DISCONNECTED`

## PM-DATA-021

**관측 순서가 복잡하고 불규칙한 활동을 어떻게 찾는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동 순서가 있는 log와 alpha 등 chaotic 판정 설정. |
| 확인할 출력 | 불규칙 활동 판정과 계산된 기준값. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | NIEK_SIDOROVA chaotic activity 기준과 alpha·활동 분포 검산. |
| 다음 작업 ID | STAT-02, DISC-06 |
| 의미·옵션·한계 | 불규칙성 계산이며 활동의 업무적 불필요성이나 오류라는 인과 판단을 직접 제공하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/statistics/chaotic_activities/algorithm.py :: apply`
- 변형 `pm4py/statistics/chaotic_activities/algorithm.py :: Variants` → `NIEK_SIDOROVA`

## PM-DATA-022

**원하는 시작·종료 활동의 case만 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case log와 허용/제외 시작·종료 활동 집합. |
| 확인할 출력 | 조건을 만족하는 전체 case들과 선택 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Boundary 조건의 case 전체 선택, positive/negative·빈 case·source-order 처리. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_start_activities`
- `pm4py/filtering.py :: filter_end_activities`

## PM-DATA-023

**이벤트·case 속성 값과 출현 비율에 따라 로그를 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Event/case 속성 조건, 수치 구간 또는 출현 비율 threshold. |
| 확인할 출력 | 조건에 따른 event slice 또는 전체 case sublog. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 이벤트 내부 삭제와 조건 만족 case 전체 선택, 수치 구간·최대 활동 수·빈도 threshold·분모. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_log_relative_occurrence_event_attribute`
- `pm4py/filtering.py :: filter_event_attribute_values`
- `pm4py/filtering.py :: filter_trace_attribute_values`
- `pm4py/algo/filtering/log/attributes/attributes_filter.py :: apply_numeric`
- `pm4py/algo/filtering/log/attributes/attributes_filter.py :: apply_numeric_events`
- `pm4py/algo/filtering/log/attributes/attributes_filter.py :: filter_log_on_max_no_activities`
- `pm4py/algo/filtering/log/attributes/attributes_filter.py :: filter_log_by_attributes_threshold`

## PM-DATA-024

**어떤 variant를 남기고 빈도·coverage를 어떻게 제한하는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Variant별 case 집합, top-k·개별/누적 coverage 조건. |
| 확인할 출력 | 선택 variant의 sublog와 coverage·동률 처리 정보. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 허용/제외 variant와 top-k 동률, 누적/개별 coverage·자동 threshold 정의. |
| 다음 작업 ID | FILTER-01, STAT-01, FILTER-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_variants`
- `pm4py/filtering.py :: filter_variants_top_k`
- `pm4py/filtering.py :: filter_variants_by_coverage_percentage`
- `pm4py/algo/filtering/log/variants/variants_filter.py :: filter_variants_by_maximum_coverage_percentage`
- `pm4py/algo/filtering/log/variants/variants_filter.py :: filter_log_variants_percentage`
- `pm4py/algo/filtering/log/variants/variants_filter.py :: filter_variants_variants_percentage`
- `pm4py/algo/filtering/log/variants/variants_filter.py :: find_auto_threshold`

## PM-DATA-025

**직접 또는 나중에 이어지는 특정 활동 관계를 가진 case를 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 활동쌍/세 활동 관계와 인접·eventual 정책. |
| 확인할 출력 | 관계 조건을 만족/위반하는 case sublog. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 인접·비인접·연속 세 활동 제약의 만족/불만족 case 선택; 반복과 strict order 정의. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_directly_follows_relation`
- `pm4py/filtering.py :: filter_eventually_follows_relation`
- `pm4py/algo/filtering/log/ltl/ltl_checker.py :: A_next_B_next_C`

## PM-DATA-026

**시간창에 포함·교차·시작·종료하는 case 또는 event를 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Event/case 시각, 시간창과 contained/intersect/start/end mode. |
| 확인할 출력 | 시간 조건에 따른 case/event 선택과 잘린 경계. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case span 선택과 event slice 구분, 경계 포함 및 timezone, 미완료 검산. |
| 다음 작업 ID | FILTER-01, FILTER-03, PERF-01 |
| 의미·옵션·한계 | log timestamp apply/apply_auto_filter는 Exception을 즉시 내는 미제공 stub이다. 실제 filter_traces_*/apply_events 계산과 구분하며 대체 기능 수에 별도 포함하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_time_range`
- `pm4py/algo/filtering/log/timestamp/timestamp_filter.py :: filter_on_trace_attribute`
- `pm4py/algo/filtering/log/timestamp/timestamp_filter.py :: filter_traces_attribute_in_timeframe`
- `pm4py/algo/filtering/log/timestamp/timestamp_filter.py :: filter_traces_starting_in_timeframe`
- `pm4py/algo/filtering/log/timestamp/timestamp_filter.py :: filter_traces_completing_in_timeframe`

## PM-DATA-027

**두 활동 사이·prefix·suffix·지정 부분열을 추출할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열, 경계 활동·prefix/suffix·부분열 조건. |
| 확인할 출력 | 추출한 구간 또는 선택 case와 원본 event 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 반복 경계의 first/last/every 규칙, event 포함 여부, 새 case ID와 원본 lineage. |
| 다음 작업 ID | FILTER-01, FILTER-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_between`
- `pm4py/filtering.py :: filter_prefixes`
- `pm4py/filtering.py :: filter_suffixes`
- `pm4py/filtering.py :: filter_trace_segments`

## PM-DATA-028

**길이·기간·재작업 횟수로 case를 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case별 길이·기간·반복 횟수, 개수/구간 조건. |
| 확인할 출력 | 조건에 맞는 case sublog와 제외 사유. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case count/size/duration·activity/attribute 반복 조건과 경계값; 빈 trace와 sample 순서. |
| 다음 작업 ID | FILTER-01, STAT-02, PERF-04 |
| 의미·옵션·한계 | log/pandas/polars case_filter.apply는 미제공 stub이며 log apply_auto_filter도 NotImplementedError를 낸다. filter_case_performance는 filter_on_case_performance alias. Polars business_hours 경로도 현재 NotImplementedError인 지원 제한을 기록한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_case_size`
- `pm4py/filtering.py :: filter_case_performance`
- `pm4py/filtering.py :: filter_activities_rework`
- `pm4py/algo/filtering/log/cases/case_filter.py :: filter_on_ncases`
- `pm4py/algo/filtering/log/attr_value_repetition/filter.py :: apply`

## PM-DATA-029

**특정 경로에 너무 오래 걸리는 case를 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case의 활동쌍 occurrence와 기간 threshold. |
| 확인할 출력 | 선택 경로의 성능 조건을 만족하는 case들. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Path occurrence별 duration threshold와 case 모집단; start/complete 기준. |
| 다음 작업 ID | FILTER-01, PERF-01, FILTER-03 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_paths_performance`

## PM-DATA-030

**동일 활동을 서로 다른 사람이 처리하거나 업무 분리가 지켜지는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 resource 속성, 업무 분리 대상 활동. |
| 확인할 출력 | Four-eyes/다른 수행자 조건의 만족·위반 case. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Four-eyes와 다른 resource 조건 필터; missing resource 및 반복 activity의 pairing. |
| 다음 작업 ID | FILTER-01, ORG-01 |
| 의미·옵션·한계 | Log/Pandas/Polars는 자료 구조 backend 차이로 묶으며 입력 순서와 결측 의미를 별도로 대조한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_four_eyes_principle`
- `pm4py/filtering.py :: filter_activity_done_different_resources`

## PM-DATA-031

**연속·동률 이벤트를 묶거나 활동 발생을 기준으로 case를 분할할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열·timestamp와 그룹/분할 또는 variant prefix/suffix 조건. |
| 확인할 출력 | 묶음·분할·선택된 case와 원본 event lineage. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 그룹화/분할은 원본 변경 view로 명시하고 새 경계·원본 event ID·삭제된 중간 이벤트를 남김. |
| 다음 작업 ID | FILTER-01, FILTER-03, IO-02 |
| 의미·옵션·한계 | Polars mirror가 있는 항목은 같은 filter family의 backend로 묶는다. 시작/끝 substring류와 활동 boundary 필터의 실제 조건을 SCOPE-02에서 구분. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/filtering/pandas/activity_split/activity_split_filter.py :: apply`
- `pm4py/algo/filtering/pandas/consecutive_act_case_grouping/consecutive_act_case_grouping_filter.py :: apply`
- `pm4py/algo/filtering/pandas/timestamp_case_grouping/timestamp_case_grouping_filter.py :: apply`
- `pm4py/algo/filtering/pandas/starts_with/starts_with_filter.py :: apply`
- `pm4py/algo/filtering/pandas/ends_with/ends_with_filter.py :: apply`

## PM-DATA-032

**DFG의 잦은 활동·경로와 특정 활동 주변 연결만 남길 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 빈도 DFG·시작/종료 빈도와 활동/경로/연결성 조건. |
| 확인할 출력 | 필터된 DFG 및 제거·유지된 원본 노드/edge 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동/edge threshold, 연결 보존·도달성·시작종료 갱신과 원본 그래프 lineage. |
| 다음 작업 ID | FILTER-01, FILTER-03, MODEL-06 |
| 의미·옵션·한계 | DFG 수치 필터는 SVG cutoff와 별개. objects/dfg/filtering 경로의 facade/alias는 추가 알고리즘으로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_dfg_activities_percentage`
- `pm4py/filtering.py :: filter_dfg_paths_percentage`
- `pm4py/algo/filtering/dfg/dfg_filtering.py :: filter_dfg_keep_connected`
- `pm4py/algo/filtering/dfg/dfg_filtering.py :: filter_dfg_to_activity`
- `pm4py/algo/filtering/dfg/dfg_filtering.py :: filter_dfg_from_activity`
- `pm4py/algo/filtering/dfg/dfg_filtering.py :: filter_dfg_contain_activity`
- `pm4py/algo/filtering/dfg/dfg_filtering.py :: clean_dfg_based_on_noise_thresh`

## PM-DATA-033

**EventLog·stream·표 형식을 의미 손실을 드러내며 오갈 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | CaseLog·event stream·표 자료와 case key·속성 scope. |
| 확인할 출력 | 대상 자료 구조와 보존/손실·원본 순서 보고. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Native CaseLog/records와 표 출력·event stream view; case metadata·빈 trace·순서·nested value 손실 계약. |
| 다음 작업 ID | IO-02, IO-05, FILTER-03 |
| 의미·옵션·한계 | PIX table→CaseLog 입력과 trace view는 존재하지만 pandas/EventLog 상호변환 API 호환성을 목표로 구현된 것은 아니다. |

**현재 PIX 근거:** `import_log`, `case_traces`.
소스: [src/pix/event_log/adapters.py](../../../src/pix/event_log/adapters.py), [src/pix/tabular/reader.py](../../../src/pix/tabular/reader.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_to_event_log`
- `pm4py/convert.py :: convert_to_event_stream`
- `pm4py/convert.py :: convert_to_dataframe`
- `pm4py/objects/conversion/log/converter.py :: apply`
- 변형 `pm4py/objects/conversion/log/converter.py :: Variants` → `TO_EVENT_LOG`, `TO_EVENT_STREAM`, `TO_DATA_FRAME`

## PM-DATA-034

**Case 로그의 이벤트·자원 관계를 graph로 볼 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case log와 DF·case/event 속성 노드 포함 설정. |
| 확인할 출력 | Event/case/attribute 노드 및 typed relation graph. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Direct-follow graph와 별개의 event/case/resource node graph 계약·변환·lineage. |
| 다음 작업 ID | REL-01, FILTER-03 |
| 의미·옵션·한계 | NetworkX라는 backend 자체를 재현할 필요보다 graph 정보·관계 의미 보존이 대체 대상이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_log_to_networkx`
- 변형 `pm4py/objects/conversion/log/converter.py :: Variants` → `TO_NX`

## PM-DATA-035

**Case의 인접 이벤트 사이 시간 구간을 추출할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 인접 event의 complete·다음 start와 선택 활동쌍. |
| 확인할 출력 | 인접 open-path interval 목록과 event 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 앞 event complete와 다음 event start 사이의 인접 interval 추출, 선택 활동쌍 필터·역전·결측·경계 해석. |
| 다음 작업 ID | IO-03, PERF-01 |
| 의미·옵션·한계 | PM4Py convert_log_to_time_intervals는 lifecycle start/complete pairing 자체가 아니라 temporally consecutive event의 open path interval을 만든다. IO-03 구간 계약과 연결하되 다른 정의로 유지한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_log_to_time_intervals`
- `pm4py/algo/transformation/log_to_interval_tree/algorithm.py :: apply`
- `pm4py/algo/transformation/log_to_interval_tree/variants/open_paths.py :: log_to_intervals`
- `pm4py/algo/transformation/log_to_interval_tree/variants/open_paths.py :: interval_to_tree`
- `pm4py/algo/transformation/log_to_interval_tree/variants/open_paths.py :: apply`
- 변형 `pm4py/algo/transformation/log_to_interval_tree/algorithm.py :: Variants` → `OPEN_PATHS`

## PM-DATA-036

**Lifecycle 이벤트를 실행 interval로 짝짓고 다시 lifecycle로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Lifecycle start/complete log 또는 interval log, instance key와 calendar. |
| 확인할 출력 | 대응시킨 실행 구간 또는 lifecycle log와 lead/cycle-time annotation. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Lifecycle start/complete의 activity+instance pairing, interval↔lifecycle 변환과 lead/cycle-time 누적 annotation; 미대응·동률·병렬 반복·business calendar 검산. |
| 다음 작업 ID | IO-03, PERF-01, PERF-04, PERF-05 |
| 의미·옵션·한계 | PM to_interval은 동일 activity/instance의 시작 event를 FIFO로 대응하며 짝 없는 complete에 start=complete를 기본 적용한다. PIX는 이러한 추정을 원본 관측과 구분하고 미대응/모호성을 명시해야 한다. 현재 service start attribute 측정은 pairing 구현이 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/log/util/interval_lifecycle.py :: to_interval`
- `pm4py/objects/log/util/interval_lifecycle.py :: to_lifecycle`
- `pm4py/objects/log/util/interval_lifecycle.py :: assign_lead_cycle_time`

## PM-OCEL-001

**객체형·속성 목록과 활동별 객체 참여 개수는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 타입 정의·속성과 E2O 관계. |
| 확인할 출력 | 객체형·속성 목록, 활동×객체형 참여 및 event cardinality. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 임의 attribute 이름과 object-type/activity 교차, event별 객체형 cardinality를 독립 결과로 제공. |
| 다음 작업 ID | STAT-01, STAT-02, REL-01 |
| 의미·옵션·한계 | PIX 구조 summary와 관계 조회는 구현됨. E2O qualifier 중복·unique object·관계행 수 구별이 필요하며 PM helper와 정확한 동일값 검증은 미완료. |

**현재 PIX 근거:** `OCEL.info`, `OCEL.objects_for_event`, `discover_ocdfg`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py), [src/pix/compute/ocdfg.py](../../../src/pix/compute/ocdfg.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_get_object_types`
- `pm4py/ocel.py :: ocel_get_attribute_names`
- `pm4py/ocel.py :: ocel_object_type_activities`
- `pm4py/ocel.py :: ocel_objects_ot_count`

## PM-OCEL-002

**동일 시각에 일어난 활동과 참여 객체들은 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL E2O와 event timestamp. |
| 확인할 출력 | 시각별 활동·객체 목록과 unique/occurrence 단위. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Timestamp별 event·activity·object aggregation; 고유 이벤트와 relation occurrence 분리. |
| 다음 작업 ID | STAT-01, STAT-03 |
| 의미·옵션·한계 | 참조는 relations를 timestamp로 groupby하여 activity/object list를 집계한다. 같은 event의 여러 E2O가 activity를 중복시킬 수 있어 unique event summary와 같지 않다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_temporal_summary`

## PM-OCEL-003

**객체별 관측 활동열·기간·상호작용 객체는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 객체별 event 참여와 timestamp. |
| 확인할 출력 | 객체별 활동열·관측 span 및 event별 상호작용 pair. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체 관측 span·activity sequence 및 event별 ordered object-pair evidence를 하나의 summary로 연결. |
| 다음 작업 ID | STAT-01, PERF-04, REL-01 |
| 의미·옵션·한계 | Trace와 관계 조회 기초는 있다. 관측 최초/마지막을 실제 객체 생성/소멸로 단정하지 않으며 관계 방향/반대 pair 중복을 명시한다. |

**현재 PIX 근거:** `reconstruct_traces`, `OCEL.events_for_object`, `OCEL.objects_for_event`.
소스: [src/pix/compute/trace.py](../../../src/pix/compute/trace.py), [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_objects_summary`
- `pm4py/ocel.py :: ocel_objects_interactions_summary`

## PM-OCEL-004

**하나의 객체형을 case로 삼아 OCEL을 펼칠 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 선택 object type, ordering·attribute 정책. |
| 확인할 출력 | 객체를 case로 한 trace/table view와 공유 event lineage. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 선택 객체형의 CaseLog/table view와 event/객체 속성·고립 객체·복제 event lineage 계약. |
| 다음 작업 ID | IO-02, OCEXEC-02, FILTER-03 |
| 의미·옵션·한계 | PIX 객체 trace 재구성은 같은 종류의 질문 일부를 답하지만 flattened table export/타입화된 CaseLog 변환과 완전동치는 아니다. 공유 event 중복을 원본 복제로 오해하지 않도록 한다. |

**현재 PIX 근거:** `reconstruct_traces`.
소스: [src/pix/compute/trace.py](../../../src/pix/compute/trace.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_flattening`
- `pm4py/objects/ocel/util/flattening.py :: flatten`

## PM-OCEL-005

**객체형마다 어떤 활동이 직접 이어지고 각 수치는 무엇을 세는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 객체형·qualifier·순서·시간집계 설정. |
| 확인할 출력 | 객체형별 OCDFG와 활동/edge 빈도·관측 시간 근거. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PM4Py events/event couples/unique objects/total occurrences를 PIX 지표와 fixture로 대조하고 business-hours edge performance 보완. |
| 다음 작업 ID | STAT-01, PERF-01, PERF-05, OCEXEC-02 |
| 의미·옵션·한계 | PIX event_pair_count·unique_object_count·occurrence_count, layer boundaries/evidence 실제구현. tie 기본 유보·qualifier 선택·O2O 비사용 등 명시 profile이며 전체 PM4Py 수치호환을 아직 증명하지 않음. |

**현재 PIX 근거:** `discover_ocdfg`, `measure_temporal`.
소스: [src/pix/compute/ocdfg.py](../../../src/pix/compute/ocdfg.py), [src/pix/compute/temporal.py](../../../src/pix/compute/temporal.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: discover_ocdfg`
- `pm4py/algo/discovery/ocel/ocdfg/algorithm.py :: apply`
- `pm4py/statistics/ocel/edge_metrics.py :: aggregate_ev_couples`
- `pm4py/statistics/ocel/edge_metrics.py :: aggregate_unique_objects`
- `pm4py/statistics/ocel/edge_metrics.py :: aggregate_total_objects`
- `pm4py/statistics/ocel/act_utils.py :: aggregate_events`
- `pm4py/statistics/ocel/act_utils.py :: aggregate_unique_objects`
- `pm4py/statistics/ocel/act_utils.py :: aggregate_total_objects`
- 변형 `pm4py/algo/discovery/ocel/ocdfg/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-006

**객체형별 net을 결합한 OCPN을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 객체형별 miner·noise·variable-arc 설정. |
| 확인할 출력 | OCPN 구조·cardinality 및 관측 수용/annotation 근거. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 발견 profile·double-arc threshold·IMf/IMd 옵션과 replay annotation의 의미대조. |
| 다음 작업 ID | DISC-01, DISC-02, MODEL-01 |
| 의미·옵션·한계 | WO_ANNOTATION과 CLASSIC는 같은 classic module Enum alias이며 별도 miner가 아니다. PIX는 관측 cardinality와 joint accepting witness를 갖는 자체 profile; PM 임계값기반 variable-arc 표시와 동일정의가 아니다. |

**현재 PIX 근거:** `discover_ocpn`.
소스: [src/pix/compute/ocpn_discovery.py](../../../src/pix/compute/ocpn_discovery.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: discover_oc_petri_net`
- `pm4py/algo/discovery/ocel/ocpn/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/ocel/ocpn/algorithm.py :: Variants` → `WO_ANNOTATION`, `CLASSIC`

## PM-OCEL-007

**공동 참여·후속·계승·동시 최초/최종 관측 관계를 graph로 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL event–object 참여와 선택 graph_type. |
| 확인할 출력 | Interaction/descendant/inheritance/cobirth/codeath 객체 edge 집합. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 다섯 graph 정의별 edge·방향·관측 순서·event 근거를 반환하고 실제 O2O와 구분. |
| 다음 작업 ID | REL-01, OCEXEC-02 |
| 의미·옵션·한계 | discover_objects_graph graph_type 문자열은 object_interaction/object_descendants/object_inheritance/object_cobirth/object_codeath. co-birth/co-death는 참조 관측경계 기준이며 실제 존재 시작/종료 보증이 아니다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: discover_objects_graph`
- `pm4py/algo/transformation/ocel/graphs/object_interaction_graph.py :: apply`
- `pm4py/algo/transformation/ocel/graphs/object_descendants_graph.py :: apply`
- `pm4py/algo/transformation/ocel/graphs/object_inheritance_graph.py :: apply`
- `pm4py/algo/transformation/ocel/graphs/object_cobirth_graph.py :: apply`
- `pm4py/algo/transformation/ocel/graphs/object_codeath_graph.py :: apply`

## PM-OCEL-008

**관측에서 유도한 객체 관계를 O2O에 추가할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 포함할 유도 객체 graph 종류. |
| 확인할 출력 | 유도 O2O가 추가된 view와 원본·derived 관계의 구분. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | Derived O2O를 원본 relation과 분리하고 qualifier·근거·중복·변경 digest를 기록. |
| 다음 작업 ID | REL-01, FILTER-03 |
| 의미·옵션·한계 | 현재 PIX O2O 보존/조회는 구현됐지만 inference graph 생성 및 enrichment는 없다. 관측 공동참여를 업무상 규범 관계로 격상하지 않는다. |

**현재 PIX 근거:** `OCEL.outgoing_o2o`, `OCEL.incoming_o2o`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_o2o_enrichment`
- `pm4py/algo/transformation/ocel/graphs/ocel20_computation.py :: apply`

## PM-OCEL-009

**객체의 최초·최종 참여를 E2O lifecycle qualifier로 표시할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL E2O 관계와 객체별 관측 순서. |
| 확인할 출력 | Creation/termination/other qualifier가 부여된 관계 view. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Creation/termination/other 관측 profile, 단일 event 객체·동률·원본 qualifier 충돌·provenance. |
| 다음 작업 ID | REL-01, REL-03, OCEXEC-02 |
| 의미·옵션·한계 | 참조는 관계행 groupby first/last를 사용하며 source table order가 개입한다. PIX는 qualifier를 보존하지만 자동 재명명 enrichment는 하지 않는다. 최초 관측=실제 생성이라는 규범 해석을 강제하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_e2o_lifecycle_enrichment`
- `pm4py/objects/ocel/util/e2o_qualification.py :: apply`

## PM-OCEL-010

**Event·object·connected component 단위로 OCEL을 표본 추출할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 표본 단위·개수·component 크기 한도·seed. |
| 확인할 출력 | 선택 ID 및 관계/이력 보존 범위를 가진 sampled OCEL. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Seed/RNG·선택 ID·관계 closure·이력 보존과 최대 event/object/E2O 크기 조건. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03, OCEXEC-04 |
| 의미·옵션·한계 | Connected component 계산 primitive는 존재해도 sampling API는 없다. 객체 표본이 다른 객체 관계를 끊는지 명시한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: sample_ocel_objects`
- `pm4py/ocel.py :: sample_ocel_connected_components`
- `pm4py/objects/ocel/util/sampling.py :: sample_ocel_events`
- `pm4py/objects/ocel/util/sampling.py :: sample_ocel_objects`

## PM-OCEL-011

**동일 관측을 중복 제거하거나 event를 병합할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 중복 key·공유 객체 조건. |
| 확인할 출력 | 중복 제거/병합 view와 원본 event/속성/관계 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 중복 판정 key·공유 객체 조건·attribute/qualifier 충돌·대표 event ID와 원본 lineage. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 참조는 activity/timestamp/object 기반 dedup 또는 activity/timestamp 병합이며 event ID 동일성 검증과 다르다. 서로 다른 동시 행동을 잘못 합치지 않도록 별도 profile/반례가 필요. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_drop_duplicates`
- `pm4py/ocel.py :: ocel_merge_duplicates`

## PM-OCEL-012

**동률 이벤트를 추가 속성으로 정렬하거나 명시적 순서로 처리할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 추가 정렬 key 또는 명시 tie policy. |
| 확인할 출력 | 순서 view 또는 합성 시각 변환본과 변경 근거. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 추가 순서 증거와 출력 view를 설계; 합성 시간 이동이 필요한 호환 출력이면 원본과 변환 근거를 분리. |
| 다음 작업 ID | OCEXEC-02, FILTER-03 |
| 의미·옵션·한계 | PIX는 timestamp tie를 기본 유보하고 event_id tie policy만 명시적 허용한다. PM index-based timedelta처럼 원본 시간에 millis를 더하는 행동을 기본 동작으로 복제하지 않는다. |

**현재 PIX 근거:** `reconstruct_traces`.
소스: [src/pix/compute/trace.py](../../../src/pix/compute/trace.py), [src/pix/contracts/analysis.py](../../../src/pix/contracts/analysis.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_sort_by_additional_column`
- `pm4py/ocel.py :: ocel_add_index_based_timedelta`

## PM-OCEL-013

**서로 연결된 객체들 또는 중심 객체의 관련 실행으로 OCEL을 나눌 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 component/ancestors-descendants 추출 설정. |
| 확인할 출력 | 분리된 실행·OCEL sublogs 및 overlap/unassigned 범위. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | Connected components와 ancestors/descendants 추출의 edge·centrality exclusion·overlap·unassigned 대조. |
| 다음 작업 ID | OCEXEC-01, OCEXEC-04, FILTER-02 |
| 의미·옵션·한계 | PIX connected_components/leading_object profile은 실제 구현. PM ANCESTORS_DESCENDANTS의 구체적 closure와 동일하다고 가정하지 않는다. |

**현재 PIX 근거:** `discover_executions`.
소스: [src/pix/compute/executions.py](../../../src/pix/compute/executions.py), [src/pix/contracts/execution.py](../../../src/pix/contracts/execution.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/ocel/split_ocel/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/ocel/split_ocel/algorithm.py :: Variants` → `CONNECTED_COMPONENTS`, `ANCESTORS_DESCENDANTS`

## PM-OCEL-014

**중심 객체 실행들이 동일한 구조인지 묶어서 설명할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 중심 object type와 max object·rename 예외 설정. |
| 확인할 출력 | 동치 실행의 군집·설명 key 또는 PIX incidence variant. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PM rename+description clustering과 PIX exact incidence graph 동치의 반례 대조, timestamp 제외·ID 예외 정책. |
| 다음 작업 ID | OCEXEC-03, FEAT-03 |
| 의미·옵션·한계 | PM cluster_equivalent_ocel은 ancestors/descendants split 후 객체 rename+VARIANT2 description key를 사용한다. PIX exact incidence 동치와 다른 정의이며 private __vectors_to_clusters 등은 facade 경로의 별도 공개 계산으로 세지 않음. |

**현재 PIX 근거:** `discover_variants`.
소스: [src/pix/compute/variants.py](../../../src/pix/compute/variants.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: cluster_equivalent_ocel`
- `pm4py/algo/transformation/ocel/description/algorithm.py :: apply`
- `pm4py/objects/ocel/util/rename_objs_ot_tim_lex.py :: apply`
- 변형 `pm4py/algo/transformation/ocel/description/algorithm.py :: Variants` → `VARIANT1`, `VARIANT2`

## PM-OCEL-015

**객체 속성 값으로 타입을 세분화하거나 다시 묶을 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 object type·분기 기준 속성. |
| 확인할 출력 | 세분화/집계된 object-type view와 원본 타입 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCEL OLAP drill-down/roll-up, tuple type encoding·missing값·원본 형식 복구·속성 이력 처리. |
| 다음 작업 ID | FILTER-02, FILTER-03, REL-02 |
| 의미·옵션·한계 | 객체 타입 변경은 inference나 원본 수정 없이 lineage 있는 projection으로 제공할지 도메인 검토가 필요. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_drill_down`
- `pm4py/ocel.py :: ocel_roll_up`
- `pm4py/algo/transformation/ocel/olap/drill_down/algorithm.py :: apply`
- `pm4py/algo/transformation/ocel/olap/roll_up/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/ocel/olap/drill_down/algorithm.py :: Variants` → `CLASSIC`
- 변형 `pm4py/algo/transformation/ocel/olap/roll_up/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-016

**객체 참여 정보를 event 타입에 펼쳤다가 되돌릴 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 event type·object type·qualifier 선택. |
| 확인할 출력 | 관계 정보를 펼치거나 접은 event-type view와 손실 보고. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OLAP fold/unfold의 event/type/qualifier·tuple naming·되돌릴 수 없는 정보 범위 검산. |
| 다음 작업 ID | FILTER-02, FILTER-03, REL-01 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ocel.py :: ocel_unfold`
- `pm4py/ocel.py :: ocel_fold`
- `pm4py/algo/transformation/ocel/olap/unfold/algorithm.py :: apply`
- `pm4py/algo/transformation/ocel/olap/fold/algorithm.py :: apply`
- 변형 `pm4py/algo/transformation/ocel/olap/unfold/algorithm.py :: Variants` → `CLASSIC`
- 변형 `pm4py/algo/transformation/ocel/olap/fold/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-017

**이벤트·객체의 속성 조건과 시간 범위로 OCEL을 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL event/object 속성 조건 또는 시간창. |
| 확인할 출력 | 조건 sublog와 관계 closure·객체 이력 경계 상태. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Event/object 필터 후 E2O/O2O closure·objectChanges 보존, 시간창 as-of 경계값. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03, REL-02 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_ocel_event_attribute`
- `pm4py/filtering.py :: filter_ocel_object_attribute`
- `pm4py/filtering.py :: filter_ocel_events_timestamp`

## PM-OCEL-018

**객체형·객체 ID·event ID를 선택하고 연결 범위를 조절할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 object/event ID·type·연결 확대 깊이. |
| 확인할 출력 | 선택 객체/event 및 연결 범위를 보존한 sublog. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 고유 ID 선택과 level별 연결 확대, 고립 객체·무관계 event·원본 source 유지. |
| 다음 작업 ID | FILTER-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 단순 tuple 조회는 있다. Sublog를 구성하며 객체/관계/이력 closure를 유지하는 필터는 아직 없다. |

**현재 PIX 근거:** `OCEL.events_by_type`, `OCEL.objects_by_type`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_ocel_object_types`
- `pm4py/filtering.py :: filter_ocel_objects`
- `pm4py/filtering.py :: filter_ocel_events`
- `pm4py/filtering.py :: filter_ocel_activities_connected_object_type`

## PM-OCEL-019

**활동과 객체형 조합·참여 개수·형별 시작/종료 이벤트를 필터링할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 활동×타입 허용표·참여 개수·관측 boundary 조건. |
| 확인할 출력 | 참여/시작/종료 조건을 만족하는 OCEL sublog. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 활동×객체형 허용 관계·per-type cardinality·관측 boundary 선택과 시간 동률 handling. |
| 다음 작업 ID | FILTER-01, FILTER-02, STAT-01, OCEXEC-02 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_ocel_object_types_allowed_activities`
- `pm4py/filtering.py :: filter_ocel_object_per_type_count`
- `pm4py/filtering.py :: filter_ocel_start_events_per_object_type`
- `pm4py/filtering.py :: filter_ocel_end_events_per_object_type`

## PM-OCEL-020

**특정 객체·크기·타입·활동이 있는 connected component만 선택할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL component와 객체·크기·type·activity 조건. |
| 확인할 출력 | 조건에 맞는 connected components의 sublog. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Execution/component 조건 선택과 boundary data·overlap·shared object 영향. |
| 다음 작업 ID | FILTER-01, FILTER-02, OCEXEC-01 |
| 의미·옵션·한계 | PIX component/execution 추출은 존재하지만 조건 필터와 원본 OCEL sublog publication은 없다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/filtering.py :: filter_ocel_cc_object`
- `pm4py/filtering.py :: filter_ocel_cc_length`
- `pm4py/filtering.py :: filter_ocel_cc_otype`
- `pm4py/filtering.py :: filter_ocel_cc_activity`

## PM-OCEL-021

**활동형–객체형 참여 graph와 빈도는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL의 활동형·객체형과 E2O 관계행. |
| 확인할 출력 | ET-OT bipartite graph와 참여 edge frequency. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | ET-OT bipartite graph와 관계행 frequency, unique event/object·qualifier 중복 분리. |
| 다음 작업 ID | STAT-01, REL-01, DISC-06 |
| 의미·옵션·한계 | 현재 OCDFG 층의 활동 근거 일부를 재사용할 수 있으나 명시 ET-OT graph/result는 미구현. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/ocel/etot/algorithm.py :: apply`
- `pm4py/discovery.py :: discover_etot`
- 변형 `pm4py/algo/discovery/ocel/etot/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-022

**객체 관계를 객체형 수준으로 묶은 OTG는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 유도 객체 graph 다섯 종류. |
| 확인할 출력 | 관계별 object-type graph와 type-pair edge frequency. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 다섯 객체 graph의 (source type,relation,target type) edge와 빈도 집계. |
| 다음 작업 ID | REL-01, DISC-06 |
| 의미·옵션·한계 | 그래프의 모집단은 원본 O2O가 아닌 참조가 유도한 interaction/descendant/inheritance/cobirth/codeath 관계. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/ocel/otg/algorithm.py :: apply`
- `pm4py/discovery.py :: discover_otg`
- 변형 `pm4py/algo/discovery/ocel/otg/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-023

**실제 OCDFG와 기준 OCDFG의 활동·경로·빈도 차이는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 관측 OCEL/OCDFG와 기준 OCDFG, 차이 threshold·가중치. |
| 확인할 출력 | 활동/flow 누락·추가·빈도 차이와 graph conformance 지표. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | GRAPH_COMPARISON의 missing/additional 및 thresholded metric differences, 가중 fitness 정의. |
| 다음 작업 ID | SCOPE-01, DISC-06, STAT-01, REL-03 |
| 의미·옵션·한계 | Joint alignment와 별개 graph-summary conformance. 참조는 type별 flow key를 합치는 단계가 있어 타입 구분 소실 반례를 검토해야 한다. SCOPE-D05: 기존 REL-03은 qualifier·시점 조건 conformance를 정의하므로 이 graph 비교 기능을 이미 포괄하지 않는다. REL-03 범위 확장 또는 별도 OCONF 작업 신설을 결정해야 하며 현재 연결은 선행 관계와 확장 제안이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/ocel/ocdfg/algorithm.py :: apply`
- `pm4py/conformance.py :: conformance_ocdfg`
- 변형 `pm4py/algo/conformance/ocel/ocdfg/algorithm.py :: Variants` → `GRAPH_COMPARISON`

## PM-OCEL-024

**실제 ET-OT·OTG와 기준 graph의 관계·빈도 차이는 무엇인가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 관측 OCEL/ET-OT/OTG와 기준 graph, threshold·가중치. |
| 확인할 출력 | 관계·노드·빈도 차이 및 graph-comparison 점수. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 노드/edge 누락·추가·빈도 차이 및 threshold/alpha/beta/gamma 조합 점수. |
| 다음 작업 ID | SCOPE-01, REL-01, REL-03, STAT-01 |
| 의미·옵션·한계 | 빈 graph/0 denominator·규범/관측 방향·결측 type와 자체 conformance 결과 계약을 검산. SCOPE-D05: 기존 REL-03은 qualifier·시점 조건 conformance를 정의하므로 이 graph 비교 기능을 이미 포괄하지 않는다. REL-03 범위 확장 또는 별도 OCONF 작업 신설을 결정해야 하며 현재 연결은 선행 관계와 확장 제안이다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/conformance/ocel/etot/algorithm.py :: apply`
- `pm4py/algo/conformance/ocel/otg/algorithm.py :: apply`
- `pm4py/conformance.py :: conformance_otg`
- `pm4py/conformance.py :: conformance_etot`
- 변형 `pm4py/algo/conformance/ocel/etot/algorithm.py :: Variants` → `GRAPH_COMPARISON`
- 변형 `pm4py/algo/conformance/ocel/otg/algorithm.py :: Variants` → `GRAPH_COMPARISON`

## PM-OCEL-025

**객체 결합의 arc-weight 분포를 가진 SAW net을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 객체형별 discovery/replay 설정. |
| 확인할 출력 | Stochastic arc-weight 분포를 갖는 SAW nets. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Stochastic arc weight net 표현 및 type별 flatten→IM→token replay로부터 weight 분포 계산. |
| 다음 작업 ID | DISC-01, MODEL-02, SIM-02 |
| 의미·옵션·한계 | PIX OCPN min/max variable cardinality는 확률 arc-weight 분포와 다르므로 SAW 구현으로 보지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/ocel/saw_nets/algorithm.py :: apply`
- 변형 `pm4py/algo/discovery/ocel/saw_nets/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-026

**연관된 두 case 로그의 교차 행동과 연결 사슬을 발견할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 연관된 두 case 표와 관계 key·timestamp·forward/propagation 옵션. |
| 확인할 출력 | Event interleavings·연결 사슬 및 통합 OCEL 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case relationship join, timestamp interleavings와 방향·forward/first/propagation 조건의 link analysis. |
| 다음 작업 ID | REL-01, OCEXEC-02, IO-05 |
| 의미·옵션·한계 | 시간의 선후와 인과를 분리하고 동률·매칭 중복·원본 ID 충돌을 공개해야 한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/discovery/ocel/interleavings/algorithm.py :: apply`
- `pm4py/algo/discovery/ocel/link_analysis/algorithm.py :: apply`
- `pm4py/objects/ocel/util/log_ocel.py :: from_interleavings`
- 변형 `pm4py/algo/discovery/ocel/interleavings/algorithm.py :: Variants` → `TIMESTAMP_INTERLEAVINGS`
- 변형 `pm4py/algo/discovery/ocel/link_analysis/algorithm.py :: Variants` → `CLASSIC`

## PM-OCEL-027

**객체별 활동열·관계 graph·속성·work-in-progress를 feature로 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL, 객체 표본·feature 선택·관측 cutoff·vocabulary. |
| 확인할 출력 | 객체별 이름·단위·mask가 있는 feature 행렬과 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Object lifecycle length/duration/unique activities/activity/path, degree/interactions/inheritance/descendants/cobirth/codeath, num/str attrs, related event/activity/object aggregations, WIP feature. |
| 다음 작업 ID | FEAT-01, FEAT-02, REL-02 |
| 의미·옵션·한계 | Feature 선택은 Parameters.ENABLE_* 플래그이며 Enum Variants dispatch가 아니다. 현재 trace/context data 보존만으로 feature 엔진을 구현한 것으로 세지 않는다. cutoff/as-of·학습 vocabulary 누출 방지 필수. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/ml.py :: extract_ocel_features`
- `pm4py/algo/transformation/ocel/features/objects/algorithm.py :: apply`
- `pm4py/algo/transformation/ocel/features/objects/algorithm.py :: transform_features_to_dict_dict`

## PM-OCEL-028

**이벤트의 시각·활동·참여 객체와 신규 관계를 feature로 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL event와 pointwise/관련 객체 feature 선택·cutoff. |
| 확인할 출력 | Event별 activity/time/attribute/relation feature 행렬. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Event activity/timestamp/attrs/object counts/type start-end/new_interactions와 related-object aggregation; observed cutoff 계약. |
| 다음 작업 ID | FEAT-01, FEAT-02, REL-01 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/ocel/features/events/algorithm.py :: apply`
- `pm4py/algo/transformation/ocel/features/events/algorithm.py :: transform_features_to_dict_dict`

## PM-OCEL-029

**각 event–object 참여 시점까지의 prefix feature를 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL의 event–object participation과 prefix feature 선택. |
| 확인할 출력 | 각 참여 시점까지의 길이·시간·활동 prefix feature. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Event pointwise + per-object prefix length/timediff/one-hot, 공동 event 중복과 미관측 future exclusion. |
| 다음 작업 ID | FEAT-01, FEAT-02, OCEXEC-02 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/ocel/features/events_objects/algorithm.py :: apply`
- `pm4py/algo/transformation/ocel/features/events_objects/prefix_features.py :: apply`

## PM-OCEL-030

**Case·표 자료를 복수 객체형을 갖는 OCEL로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | CaseLog 또는 업무 표, 활동/시각·객체형·구분자·속성 mapping. |
| 확인할 출력 | OCEL projection과 원본 ID·메타데이터 보존/손실 보고. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 참조 separator/list/object-attribute profile 대조, 표 mapping과 explicit case bridge의 보존·손실 증거. |
| 다음 작업 ID | IO-05, FILTER-03 |
| 의미·옵션·한계 | PIX explicit mapping과 원본 CaseLog를 붙인 projection은 구현됨. 누락 timestamp·nested 값 등의 제한과 PM 암묵적 object_type 추정/구분자 파싱을 동일시하지 않음. |

**현재 PIX 근거:** `to_ocel`, `import_log`, `OCELTableMapping`, `CaseOCELMapping`.
소스: [src/pix/event_log/adapters.py](../../../src/pix/event_log/adapters.py), [src/pix/tabular/reader.py](../../../src/pix/tabular/reader.py), [src/pix/tabular/mapping.py](../../../src/pix/tabular/mapping.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-XES](../../../docs/version/v0.5.0_XES_CORPUS_2026-09-13.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_log_to_ocel`
- `pm4py/objects/ocel/util/log_ocel.py :: from_traditional_log`
- `pm4py/objects/ocel/util/log_ocel.py :: from_traditional_pandas`
- `pm4py/objects/ocel/util/log_ocel.py :: log_to_ocel_multiple_obj_types`
- `pm4py/objects/ocel/util/extended_table.py :: get_ocel_from_extended_table`

## PM-OCEL-031

**OCEL의 event/object/직접후속 또는 object feature 관계를 graph로 변환할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 event/object graph 또는 object-feature graph variant. |
| 확인할 출력 | Typed event/object/DF 또는 object-feature relation graph. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | OCEL_TO_NX의 relation+DF 및 OCEL_FEATURES_TO_NX의 object graph 표현과 edge evidence. |
| 다음 작업 ID | REL-01, FEAT-02, FILTER-03 |
| 의미·옵션·한계 | NetworkX 의존 자체 대신 graph 구조를 보존하는 PIX contract/선택 adapter로 대체할 수 있다. 현재 viewer는 이 데이터 graph 변환 API가 아님. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/convert.py :: convert_ocel_to_networkx`
- `pm4py/objects/conversion/ocel/converter.py :: apply`
- 변형 `pm4py/objects/conversion/ocel/converter.py :: Variants` → `OCEL_TO_NX`, `OCEL_FEATURES_TO_NX`

## PM-OCEL-032

**속성을 객체로 승격하거나 object-event 관계를 explode하고 부모–자식 참조를 만들 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL과 승격할 속성·explode·parent/child 조건. |
| 확인할 출력 | 새 객체/관계/복제 event view와 원본 lineage. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 객체화/explode/parent-child ref의 identity·새 관계·attribute 보존 및 다대다 정보 손실을 명시. |
| 다음 작업 ID | REL-01, FILTER-02, FILTER-03 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/ocel/util/ev_att_to_obj_type.py :: apply`
- `pm4py/objects/ocel/util/explode.py :: apply`
- `pm4py/objects/ocel/util/parent_children_ref.py :: apply`

## PM-OCEL-033

**OCEL의 관계 multiplicity 때문에 flattening에 convergence/divergence가 생기는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL E2O의 활동×객체형 참여 multiplicity. |
| 확인할 출력 | Convergence/divergence 진단과 원인 관계 집합. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Convergence/divergence 진단과 활동×객체형 evidence; multiplicity와 불필요한 복제 연결을 구별. |
| 다음 작업 ID | STAT-01, REL-01, IO-02 |
| 의미·옵션·한계 | 고정한 PM4Py 2.7.23.8 배포 소스의 계산 목록. 같은 명칭만으로 PIX와의 동치성을 인정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/ocel/util/convergence_divergence_diagnostics.py :: apply`

## PM-OCEL-034

**시점별 객체 상태·qualifier를 보존하고 조회 가능한 형식으로 전달할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL O2O/E2O·object assignment 이력과 선택 시점/필터. |
| 확인할 출력 | 보존된 관계/이력 sublog 및 제안 as-of 상태 조회 근거. |
| 현재 PIX | 부분 대응 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PIX object attribute assignment에서 as-of query와 filter boundary state, qualified relations 기반 계산 연결. |
| 다음 작업 ID | REL-01, REL-02, REL-03, FILTER-02 |
| 의미·옵션·한계 | 이 행의 참조 symbols는 필터 전파 중 o2o/object_changes 보존 경로를 추적한다. PM4Py 전체에 표준 as-of evaluator가 있다는 주장은 하지 않는다. PIX의 시점별 상태 계산은 사용자 요구로 보강할 부분. |

**현재 PIX 근거:** `OCEL.outgoing_o2o`, `OCEL.incoming_o2o`, `OCEL.e2o_for_event`.
소스: [src/pix/ocel/model.py](../../../src/pix/ocel/model.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/objects/ocel/util/filtering_utils.py :: propagate_event_filtering`
- `pm4py/objects/ocel/util/filtering_utils.py :: propagate_object_filtering`
- `pm4py/objects/ocel/util/filtering_utils.py :: propagate_relations_filtering`

## PM-IO-001

**XES와 gzip XES를 case·기록 순서·classifier·중첩 속성을 보존하여 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | XES/.xes.gz 파일과 activity/classifier·import 정책. |
| 확인할 출력 | 원본 순서·중첩 메타데이터를 보존한 CaseLog와 import 증거. |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 고정 판본의 지원 profile별 XES 대조와 native CaseLog 분석 연결을 완성한다. bytes deserialize·특정 backend 반환형을 대체할 필요는 의미/사용 시나리오로 결정한다. |
| 다음 작업 ID | IO-01, IO-02, IO-05 |
| 의미·옵션·한계 | PIX는 원본 순서와 metadata를 보존하는 immutable CaseLog를 반환한다. PM4Py의 DataFrame/EventLog/Polars 및 timestamp 정렬 경로와 동일 반환형을 주장하지 않는다. 위 여섯 selector는 입력 backend 목록이며 여섯 알고리즘의 재구현 요구로 세지 않는다. 실제 XES 검증 근거는 E-XES의 명시 범위다. MXML import는 PIX에 별도 존재하나 이 PM4Py wheel의 read.py와 objects/log/importer에는 MXML importer가 없어 PM4Py 기능으로 기재하지 않는다. |

**현재 PIX 근거:** `import_xes`, `read_xes`, `import_log`, `read_log`.
소스: [src/pix/event_log/reader.py](../../../src/pix/event_log/reader.py), [src/pix/event_log/model.py](../../../src/pix/event_log/model.py), [src/pix/io.py](../../../src/pix/io.py).
실행 기록: [E-XES](../../../docs/version/v0.5.0_XES_CORPUS_2026-09-13.md), [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_xes`
- `pm4py/objects/log/importer/xes/importer.py :: apply`
- `pm4py/objects/log/importer/xes/importer.py :: deserialize`
- 변형 `pm4py/objects/log/importer/xes/importer.py :: Variants` → `ITERPARSE`, `LINE_BY_LINE`, `ITERPARSE_MEM_COMPRESSED`, `ITERPARSE_20`, `CHUNK_REGEX`, `RUSTXES`

## PM-IO-002

**CaseLog를 XES로 내보내 다른 분석 도구에 전달할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | CaseLog와 XES 출력 profile·압축 옵션. |
| 확인할 출력 | XES/.xes.gz 파일과 보존/손실·왕복 검증 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | XES writer·gzip·메모리 직렬화 사용 시나리오와 손실/표현 불가 계약을 정하고 metadata·classifier·중첩 속성·빈 trace·원본 순서 왕복을 검증한다. |
| 다음 작업 ID | IO-04, IO-05 |
| 의미·옵션·한계 | 현재 CaseLog import와 OCEL 투영은 XES export의 구현 근거가 아니다. MXML writer는 사용자 요구 기반 IO-04에 함께 남아 있지만 PM4Py 대응 기능으로 집계하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/event_log/model.py](../../../src/pix/event_log/model.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/write.py :: write_xes`
- `pm4py/objects/log/exporter/xes/exporter.py :: apply`
- `pm4py/objects/log/exporter/xes/exporter.py :: serialize`
- 변형 `pm4py/objects/log/exporter/xes/exporter.py :: Variants` → `ETREE`, `LINE_BY_LINE`

## PM-IO-003

**기본 OCEL 1 JSON을 객체·이벤트 손실을 설명하며 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 1 또는 enriched legacy JSON 파일과 strict profile. |
| 확인할 출력 | 정규화 OCEL과 원본 증거·미지원 enriched 요소 진단. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | 기본 OCEL 1 profile 외 PM4Py enriched legacy JSON의 typedOmap·O2O·objectChanges를 별도 호환 profile로 구현/명시하고 최신 wheel fixture로 대조한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | 기본 OCEL 1 JSON reader는 구현되어 있다. 그러나 PM4Py CLASSIC은 비표준 enriched 요소도 읽고 PIX strict legacy 허용 필드는 이를 포함하지 않으므로 전체 CLASSIC 대응은 partial이다. Legacy globals의 canonical 미보존은 transformation으로 공개한다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/legacy.py](../../../src/pix/ocel/ingest/formats/legacy.py), [src/pix/ocel/ingest/reader.py](../../../src/pix/ocel/ingest/reader.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel`
- `pm4py/read.py :: read_ocel_json`
- `pm4py/objects/ocel/importer/jsonocel/variants/classic.py :: get_base_ocel`
- `pm4py/objects/ocel/importer/jsonocel/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/jsonocel/importer.py :: Variants` → `CLASSIC`, `OCEL20_STANDARD`, `OCEL20_RUSTXES`

## PM-IO-004

**OCEL 1 XML에서 이벤트·객체·속성 타입을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 1 no-namespace XML 파일. |
| 확인할 출력 | 타입화된 OCEL과 명시한 legacy 변환·진단. |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | 고정 판본·생산자별 XML profile와 비표준 입력의 수용/거절 차이를 대조하고 실제 fixture를 보완한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PIX의 선언된 OCEL 1 no-namespace XML 범위에 한정한다. 임의 XML 방언 전체 수용이나 PM4Py 오류 동작 복제를 의미하지 않는다. OCEL20와 OCEL20_RUSTXES는 같은 selector 소속이지만 PM-IO-008에서 따로 다룬다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/legacy.py](../../../src/pix/ocel/ingest/formats/legacy.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel`
- `pm4py/read.py :: read_ocel_xml`
- `pm4py/objects/ocel/importer/xmlocel/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/xmlocel/importer.py :: Variants` → `CLASSIC`, `OCEL20`, `OCEL20_RUSTXES`

## PM-IO-005

**PM4Py classic 3-table SQLite 로그를 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | PM4Py classic 3-table 단일 SQLite 파일. |
| 확인할 출력 | 정규화 OCEL과 DB profile·원본 hash·변환 증거. |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | 최신 배포판의 EVENTS/OBJECTS/RELATIONS fixture를 대조하고 producer별 타입·결측·중복 처리 차이를 기록한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PIX는 닫힌 단일 rollback-journal DB profile이다. WAL/sidecar가 있는 활성 DB를 단일파일 증거처럼 읽지 않는다. 이 형식은 OCEL 2 표준 SQLite와 다르며 기존 compatibility 근거는 PM4Py 3329bbcb 판본이다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/legacy_sqlite.py](../../../src/pix/ocel/ingest/formats/legacy_sqlite.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel`
- `pm4py/read.py :: read_ocel_sqlite`
- `pm4py/objects/ocel/importer/sqlite/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/sqlite/importer.py :: Variants` → `PANDAS_IMPORTER`, `OCEL20`

## PM-IO-006

**PM4Py의 기존 extended-table CSV와 선택적 객체 CSV를 가져오는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | PM4Py extended event CSV와 선택 object CSV·mapping. |
| 확인할 출력 | 두 표의 객체 관계를 해석한 OCEL 및 dialect 진단. |
| 현재 PIX | 부분 대응 · 일부 의미 겹침 · 참조 대체 승인 전 |
| 남은 개발·검증 | PM4Py extended CSV의 객체 목록 문자열·별도 objects_path·object metadata 결합을 명시적 compatibility profile로 구현하고 원본/변환 증거를 보존한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PIX generic table mapping은 scalar/separator/JSON object 목록을 지원하지만 Python-list 기반 PM4Py CSV 방언 자동 인식이나 별도 objects_path 결합을 제공하지 않는다. OCEL 2.1 compact CSV import는 이 기능의 대체가 아니다. |

**현재 PIX 근거:** `import_table`, `import_log`.
소스: [src/pix/tabular/reader.py](../../../src/pix/tabular/reader.py), [src/pix/tabular/mapping.py](../../../src/pix/tabular/mapping.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel`
- `pm4py/read.py :: read_ocel_csv`
- `pm4py/objects/ocel/importer/csv/importer.py :: apply`
- `pm4py/objects/ocel/importer/csv/variants/pandas.py :: apply`
- 변형 `pm4py/objects/ocel/importer/csv/importer.py :: Variants` → `PANDAS`, `OCEL20`

## PM-IO-007

**표준 OCEL 2 JSON의 타입·qualifier·O2O·속성 이력을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 2 JSON/JSON gzip 파일. |
| 확인할 출력 | 타입·qualifier·O2O·객체 이력을 보존한 OCEL과 진단. |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | 고정 PM4Py 판본/생산자별 JSON fixture와 타입·시간·null·중복 경계의 수용/거절을 대조한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PIX canonical primitive/time profile 범위에서 구현된다. PM4Py OCEL20_STANDARD와 Rust backend의 모든 수용 차이 또는 표준 전체 certification은 미입증이다. JSON gzip 입력을 지원한다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/json.py](../../../src/pix/ocel/ingest/formats/json.py), [src/pix/ocel/ingest/formats/common.py](../../../src/pix/ocel/ingest/formats/common.py).
실행 기록: [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel2`
- `pm4py/read.py :: read_ocel2_json`
- `pm4py/objects/ocel/importer/jsonocel/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/jsonocel/importer.py :: Variants` → `CLASSIC`, `OCEL20_STANDARD`, `OCEL20_RUSTXES`

## PM-IO-008

**OCEL 2 XML의 타입·관계·시점별 속성을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 2 XML/XML gzip 파일. |
| 확인할 출력 | 선언된 XML profile의 OCEL과 관계·시각 검증 결과. |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | XML 생산자별 namespace/relationship 직렬화 profile과 타입·시간 표현 경계를 대조한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PIX의 선언된 XML profile 및 gzip 입력 범위다. PM4Py OCEL20/OCEL20_RUSTXES backend 선택을 그대로 재현할 필요와 의미 호환을 구분한다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/xml.py](../../../src/pix/ocel/ingest/formats/xml.py), [src/pix/ocel/ingest/formats/common.py](../../../src/pix/ocel/ingest/formats/common.py).
실행 기록: [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel2`
- `pm4py/read.py :: read_ocel2_xml`
- `pm4py/objects/ocel/importer/xmlocel/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/xmlocel/importer.py :: Variants` → `CLASSIC`, `OCEL20`, `OCEL20_RUSTXES`

## PM-IO-009

**OCEL 2 SQLite 타입별 테이블·관계·속성 이력을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | OCEL 2 SQLite 단일 파일. |
| 확인할 출력 | 타입별 테이블·관계·이력을 정규화한 OCEL. |
| 현재 PIX | 구현 있음 · 명시한 좁은 범위 대응 · 참조 대체 승인 전 |
| 남은 개발·검증 | 최신 wheel의 타입 테이블 mapping과 실제 DB fixture를 대조하고 integer/float/time/이름 충돌 경계 근거를 보완한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | OCEL20 SQLite와 classic PANDAS_IMPORTER는 별개 profile이다. DB를 읽는 것과 generic DB connector를 제공하는 것은 다르다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/sqlite.py](../../../src/pix/ocel/ingest/formats/sqlite.py).
실행 기록: [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel2`
- `pm4py/read.py :: read_ocel2_sqlite`
- `pm4py/objects/ocel/importer/sqlite/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/sqlite/importer.py :: Variants` → `PANDAS_IMPORTER`, `OCEL20`

## PM-IO-010

**Compact OCEL CSV의 객체 참조·qualifier·속성 이력을 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Compact OCEL CSV와 2.1.0pre4 해석 profile. |
| 확인할 출력 | 객체 참조·qualifier·assignment가 정규화된 OCEL. |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | 고정 PM4Py OCEL20 CSV 구현과 PIX 2.1.0pre4 profile의 escape·타입추론·첫 시점·null 차이를 fixture별로 대조한다. 이후 규격 변경은 별도 versioned profile로 검토한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PM4Py API/selector 명칭은 OCEL20지만 PIX 규범은 2026-08-24 OCEL 2.1.0pre4 PDF다. Canonical OCEL 2.0으로 정규화하며 null은 거절, 명시적 속성 시점을 보존한다. 최신 2.1 전체 준수로 확대하지 않는다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/compact.py](../../../src/pix/ocel/ingest/formats/compact.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel2`
- `pm4py/read.py :: read_ocel2_csv`
- `pm4py/objects/ocel/importer/csv/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/csv/importer.py :: Variants` → `PANDAS`, `OCEL20`

## PM-IO-011

**CSV/Parquet OCEL bundle을 디렉터리 또는 ZIP에서 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Metadata를 가진 CSV/Parquet OCEL bundle directory/ZIP. |
| 확인할 출력 | Bundle metadata에 따라 읽은 OCEL과 파일별 import 증거. |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | CSV/Parquet·ZIP/directory·metadata/types의 고정 판본별 교환 fixture를 확대하고 schema/profile 차이를 문서화한다. |
| 다음 작업 ID | IO-01, IO-05 |
| 의미·옵션·한계 | PIX는 2.1.0pre4의 bundle format 1.0 profile이다. Metadata를 권위로 사용하며 Parquet은 선택 의존성이다. PM4Py 이름 OCEL20을 최신 표준 전체 호환의 증거로 해석하지 않는다. |

**현재 PIX 근거:** `import_ocel`, `read_ocel`.
소스: [src/pix/ocel/ingest/formats/bundled.py](../../../src/pix/ocel/ingest/formats/bundled.py), [src/pix/ocel/ingest/formats/_bundle_tables.py](../../../src/pix/ocel/ingest/formats/_bundle_tables.py), [src/pix/ocel/ingest/formats/_bundle_source.py](../../../src/pix/ocel/ingest/formats/_bundle_source.py).
실행 기록: [E-IMPORT](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ocel2`
- `pm4py/read.py :: read_ocel2_bundle`
- `pm4py/objects/ocel/importer/bundled/importer.py :: apply`
- 변형 `pm4py/objects/ocel/importer/bundled/importer.py :: Variants` → `OCEL20`

## PM-IO-012

**Canonical 객체 로그를 OCEL 2 JSON/XML/SQLite로 보존하여 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 유효한 PIX OCEL, JSON/XML/SQLite 출력 profile과 목적 경로. |
| 확인할 출력 | 재수입 digest 일치를 확인한 OCEL 2 파일과 publication 결과. |
| 현재 PIX | 구현 있음 · PIX 자체 정의 · 참조 대체 승인 전 |
| 남은 개발·검증 | PM4Py와 실제 생산자/소비자의 교환 fixture를 보완하고 지원 profile 경계를 검증한다. |
| 다음 작업 ID | IO-01, IO-04, IO-05 |
| 의미·옵션·한계 | PIX writer는 JSON·XML·SQLite 모두 구현되어 있으며 re-import canonical digest 일치 후 atomic publish한다. JSON/XML gzip 지원, SQLite gzip 미지원. SQLite int64·negative zero·열 이름 충돌 또는 XML 표현 불가를 손실 변환하지 않고 거절한다. PIX XML 출력은 no-namespace relobj profile이다. |

**현재 PIX 근거:** `export_ocel`.
소스: [src/pix/ocel/export/writer.py](../../../src/pix/ocel/export/writer.py).
실행 기록: [E-OCEL](../../../docs/version/v0.5.0_IMPORT_IMPLEMENTATION.md), [E-NATIVE](../../../docs/version/v0.3.0_NATIVE_ENGINE_IMPLEMENTATION.md).

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/write.py :: write_ocel2`
- `pm4py/write.py :: write_ocel2_json`
- `pm4py/write.py :: write_ocel2_xml`
- `pm4py/write.py :: write_ocel2_sqlite`
- `pm4py/objects/ocel/exporter/jsonocel/exporter.py :: apply`
- `pm4py/objects/ocel/exporter/xmlocel/exporter.py :: apply`
- `pm4py/objects/ocel/exporter/sqlite/exporter.py :: apply`
- 변형 `pm4py/objects/ocel/exporter/jsonocel/exporter.py :: Variants` → `CLASSIC`, `OCEL20`, `OCEL20_STANDARD`
- 변형 `pm4py/objects/ocel/exporter/xmlocel/exporter.py :: Variants` → `CLASSIC`, `OCEL20`
- 변형 `pm4py/objects/ocel/exporter/sqlite/exporter.py :: Variants` → `PANDAS_EXPORTER`, `OCEL20`

## PM-IO-013

**기존 OCEL 1/PM4Py enriched JSON·XML·CSV·classic SQLite로 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | PIX OCEL과 legacy/enriched JSON·XML·CSV·SQLite 출력 profile. |
| 확인할 출력 | 지정한 legacy 파일과 정보 손실 또는 표현 불가 보고. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 형식별 writer 및 representability/손실 계약을 구현하고 qualifier·O2O·이력의 보존 또는 공개된 거절을 검증한다. |
| 다음 작업 ID | IO-04, IO-05 |
| 의미·옵션·한계 | PM4Py write_ocel_json은 로그의 is_ocel20에 따라 CLASSIC 또는 enriched OCEL20을 선택한다. 표준 OCEL2 JSON writer(OCEL20_STANDARD)와 별개다. PIX의 현재 OCEL2 exporter가 이전 dialect 출력을 대신하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/ocel/export/writer.py](../../../src/pix/ocel/export/writer.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/write.py :: write_ocel`
- `pm4py/write.py :: write_ocel_json`
- `pm4py/write.py :: write_ocel_xml`
- `pm4py/write.py :: write_ocel_csv`
- `pm4py/write.py :: write_ocel_sqlite`
- 변형 `pm4py/objects/ocel/exporter/jsonocel/exporter.py :: Variants` → `CLASSIC`, `OCEL20`, `OCEL20_STANDARD`
- 변형 `pm4py/objects/ocel/exporter/xmlocel/exporter.py :: Variants` → `CLASSIC`, `OCEL20`
- 변형 `pm4py/objects/ocel/exporter/csv/exporter.py :: Variants` → `PANDAS`, `OCEL20`
- 변형 `pm4py/objects/ocel/exporter/sqlite/exporter.py :: Variants` → `PANDAS_EXPORTER`, `OCEL20`

## PM-IO-014

**Compact CSV와 CSV/Parquet bundle을 다른 도구에 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | PIX OCEL과 compact CSV 또는 CSV/Parquet bundle 출력 설정. |
| 확인할 출력 | 선택 교환 profile의 파일·bundle 및 round-trip 증거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 목표 pre4/호환 profile을 선택한 compact/bundle writer·정밀도/타입·metadata·ZIP/directory export와 왕복을 구현한다. |
| 다음 작업 ID | IO-04, IO-05 |
| 의미·옵션·한계 | PIX에는 두 형식의 importer만 있다. CSV compact와 Parquet bundle은 같은 물리 형식으로 묶지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/ocel/export/writer.py](../../../src/pix/ocel/export/writer.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/write.py :: write_ocel2`
- `pm4py/write.py :: write_ocel2_csv`
- `pm4py/write.py :: write_ocel2_bundle`
- `pm4py/objects/ocel/exporter/csv/exporter.py :: apply`
- `pm4py/objects/ocel/exporter/bundled/exporter.py :: apply`
- 변형 `pm4py/objects/ocel/exporter/csv/exporter.py :: Variants` → `PANDAS`, `OCEL20`
- 변형 `pm4py/objects/ocel/exporter/bundled/exporter.py :: Variants` → `OCEL20`

## PM-IO-015

**PNML 모델/구조 파일을 읽고 다시 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | PNML 파일 또는 PN 모델과 marking·weight·확장 속성. |
| 확인할 출력 | 읽은 PN 모델 또는 PNML 파일과 미지원 요소·손실 보고. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | PNML reader/writer와 ID·marking/경계·weight·silent/확장 속성 등 해당 모델 의미의 보존/손실 계약을 구현한다. |
| 다음 작업 ID | MODEL-03, IO-05 |
| 의미·옵션·한계 | 현재 PIX model/result JSON은 이 교환 형식의 대체가 아니다. 모델 표현·변환 inventory 팀과 동일 작업 MODEL-03에 합쳐 집계할 수 있다. 이 행은 파일 교환만 다루며 발화/발견 의미 구현 여부를 판정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/models.py](../../../src/pix/models.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_pnml`
- `pm4py/write.py :: write_pnml`
- `pm4py/objects/petri_net/importer/importer.py :: apply`
- `pm4py/objects/petri_net/exporter/exporter.py :: apply`
- 변형 `pm4py/objects/petri_net/importer/importer.py :: Variants` → `PNML`
- 변형 `pm4py/objects/petri_net/exporter/exporter.py :: Variants` → `PNML`

## PM-IO-016

**PTML 모델/구조 파일을 읽고 다시 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | PTML 파일 또는 process tree. |
| 확인할 출력 | 읽은 process tree 또는 PTML 파일과 구조 보존 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | PTML reader/writer와 ID·marking/경계·weight·silent/확장 속성 등 해당 모델 의미의 보존/손실 계약을 구현한다. |
| 다음 작업 ID | MODEL-03, IO-05 |
| 의미·옵션·한계 | 현재 PIX model/result JSON은 이 교환 형식의 대체가 아니다. 모델 표현·변환 inventory 팀과 동일 작업 MODEL-03에 합쳐 집계할 수 있다. 이 행은 파일 교환만 다루며 발화/발견 의미 구현 여부를 판정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/models.py](../../../src/pix/models.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_ptml`
- `pm4py/write.py :: write_ptml`
- `pm4py/objects/process_tree/importer/importer.py :: apply`
- `pm4py/objects/process_tree/exporter/exporter.py :: apply`
- 변형 `pm4py/objects/process_tree/importer/importer.py :: Variants` → `PTML`
- 변형 `pm4py/objects/process_tree/exporter/exporter.py :: Variants` → `PTML`

## PM-IO-017

**DFG 모델/구조 파일을 읽고 다시 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | DFG 파일 또는 활동·경로·시작/종료 빈도 graph. |
| 확인할 출력 | 읽은 DFG 또는 DFG 교환 파일과 빈도·경계 보존 결과. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | DFG reader/writer와 ID·marking/경계·weight·silent/확장 속성 등 해당 모델 의미의 보존/손실 계약을 구현한다. |
| 다음 작업 ID | MODEL-03, IO-05 |
| 의미·옵션·한계 | 현재 PIX model/result JSON은 이 교환 형식의 대체가 아니다. 모델 표현·변환 inventory 팀과 동일 작업 MODEL-03에 합쳐 집계할 수 있다. 이 행은 파일 교환만 다루며 발화/발견 의미 구현 여부를 판정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/models.py](../../../src/pix/models.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_dfg`
- `pm4py/write.py :: write_dfg`
- `pm4py/objects/dfg/importer/importer.py :: apply`
- `pm4py/objects/dfg/exporter/exporter.py :: apply`
- 변형 `pm4py/objects/dfg/importer/importer.py :: Variants` → `CLASSIC`
- 변형 `pm4py/objects/dfg/exporter/exporter.py :: Variants` → `CLASSIC`

## PM-IO-018

**BPMN 모델/구조 파일을 읽고 다시 내보내는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | BPMN 파일 또는 BPMN 모델·확장 속성. |
| 확인할 출력 | 읽은 BPMN 또는 BPMN 파일과 지원 요소·손실 보고. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | BPMN reader/writer와 ID·marking/경계·weight·silent/확장 속성 등 해당 모델 의미의 보존/손실 계약을 구현한다. |
| 다음 작업 ID | MODEL-03, IO-05 |
| 의미·옵션·한계 | 현재 PIX model/result JSON은 이 교환 형식의 대체가 아니다. 모델 표현·변환 inventory 팀과 동일 작업 MODEL-03에 합쳐 집계할 수 있다. 이 행은 파일 교환만 다루며 발화/발견 의미 구현 여부를 판정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/models.py](../../../src/pix/models.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_bpmn`
- `pm4py/write.py :: write_bpmn`
- `pm4py/objects/bpmn/importer/importer.py :: apply`
- `pm4py/objects/bpmn/exporter/exporter.py :: apply`
- 변형 `pm4py/objects/bpmn/importer/importer.py :: Variants` → `LXML`
- 변형 `pm4py/objects/bpmn/exporter/exporter.py :: Variants` → `ETREE`

## PM-IO-019

**HTTP/HTTPS 로그 주소를 입력하여 출처와 원본 파일을 확보한 뒤 읽는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | HTTP/HTTPS 로그 URL과 획득·timeout·출처 정책. |
| 확인할 출력 | 원본 byte/hash와 source URL을 가진 로컬 입력 증거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | URL 획득을 계산 코어와 분리한 source adapter로 제공할지 정하고, 제공 시 URI·응답/콘텐츠 식별·원본 hash·저장 파일을 연결한다. |
| 다음 작업 ID | IO-05 |
| 의미·옵션·한계 | PM4Py read.py의 일부 상위 read 함수는 HTTP/HTTPS를 임시파일로 내려받는다. PIX 입력은 현재 로컬 경로/명시적 table records다. 이 항목은 전송 편의 기능이며 계산 알고리즘 공수로 세지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
검토 참고 소스(해당 기능 구현 아님): [src/pix/io.py](../../../src/pix/io.py), [src/pix/ocel/ingest/reader.py](../../../src/pix/ocel/ingest/reader.py).
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/read.py :: read_xes`
- `pm4py/read.py :: read_ocel`
- `pm4py/read.py :: read_ocel2`
- `pm4py/read.py :: _resolve_path`

## PM-DATA-037

**분석용 가상 시작·종료 이벤트를 명시적으로 추가할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case log와 가상 start/end 활동명·시각 부여 정책. |
| 확인할 출력 | 원본과 가상 이벤트가 구분된 분석 view 및 ID lineage. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | 경계 event 추가의 activity 충돌·empty case·시각 가정 및 원본 event와의 분리. |
| 다음 작업 ID | IO-02, FILTER-03 |
| 의미·옵션·한계 | PIX 현재 DFG 시작/종료 count는 실제 가상 event 삽입 API가 아니다. 합성 데이터가 원본 행동으로 기록되지 않게 한다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: insert_artificial_start_end`

## PM-DATA-038

**Case 전체의 service·sojourn·waiting을 집계하여 붙일 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case의 start/complete interval과 합집합·calendar 정책. |
| 확인할 출력 | Case별 service/sojourn/waiting annotation 및 interval 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Case별 처리 구간 union과 관측 span·잔여 대기 수식; 병렬 구간과 미관측 기간 검산. |
| 다음 작업 ID | IO-03, PERF-01, PERF-04, PERF-05 |
| 의미·옵션·한계 | 활동별 service time과 case 전체 합계/union은 다른 모집단이다. Reference의 waiting 산출을 실제 대기 상태 관측으로 단정하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/analysis.py :: insert_case_service_waiting_time`

## PM-DATA-039

**동일 활동 라벨을 전후 문맥에 따라 구분할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열, 대상 활동·prefix/suffix 길이·edge threshold. |
| 확인할 출력 | 문맥별로 분리된 activity label과 원본 event 대응. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | CONTEXTUAL의 prefix/suffix 문맥·편집거리·clustering과 새 라벨 생성, 원본 classification 보존. |
| 다음 작업 ID | STAT-02, FEAT-03, FILTER-03 |
| 의미·옵션·한계 | Reference 문맥 유사도와 label split은 domain의 실제 업무 종류 차이를 증명하지 않는다. 학습집합과 변환 적용집합을 구분. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/label_splitting/algorithm.py :: apply`
- 변형 `pm4py/algo/label_splitting/algorithm.py :: Variants` → `CONTEXTUAL`

## PM-DATA-040

**서로 연관된 case 관계표를 사용해 두 로그를 결합할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | 두 case table과 left/right case 관계표, timestamp/key 설정. |
| 확인할 출력 | 관계로 결합한 case table과 원본 case/event lineage. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | PANDAS case-relations join의 다대다 중복·시각 정렬·ID 충돌·속성 충돌 검산. |
| 다음 작업 ID | IO-05, REL-01, FILTER-03 |
| 의미·옵션·한계 | 연결된 case의 집계는 단일 원본 case와 같지 않다. Native merge view에서 duplicated occurrence와 unique event를 구분. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/merging/case_relations/algorithm.py :: apply`
- 변형 `pm4py/algo/merging/case_relations/algorithm.py :: Variants` → `PANDAS`

## PM-DATA-041

**활동열의 공통 prefix를 trie 구조로 표현할 수 있는가?**

| 검토 항목 | 내용 |
|---|---|
| 입력 | Case 활동열과 activity key·max path length. |
| 확인할 출력 | 공통 prefix를 공유하는 trie와 terminal/중복 관측 근거. |
| 현재 PIX | 대응 구현 없음 · 미구현 · 참조 대체 승인 전 |
| 남은 개발·검증 | Trie 노드/terminal·빈 trace·반복 variant·길이 한도 처리 및 prefix tree discovery와 연결. |
| 다음 작업 ID | DISC-06, MODEL-02, STAT-01 |
| 의미·옵션·한계 | 상위 discover_prefix_tree는 core DISC행이 소유한다. 이 저수준 log_to_trie는 같은 구조 생성의 구현 경로이며 별개 알고리즘 수로 중복 집계하지 않는다. |

**현재 PIX 근거:** 대응 API 없음.
소스: 대응 구현 없음.
실행 기록: 해당 기능의 PIX 실행 검증 없음.

**참조 소스:** `pm4py 2.7.23.8` 공식 wheel. 함수·변형은 다음과 같다.

- `pm4py/algo/transformation/log_to_trie/algorithm.py :: apply`
