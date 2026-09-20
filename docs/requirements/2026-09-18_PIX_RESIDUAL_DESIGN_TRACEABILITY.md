# PIX 잔여 177개 설계 추적표

작성: 2026-09-18. 구현 상태가 아니라 설계 처리 상태다. 원래 체크·메모는 [공동 검토표](2026-09-18_PIX_REMAINING_177_JOINT_REVIEW_CHECKLIST.md)에 보존한다. 대화에서 확정한 “수집은 Agent, 계산은 PIX”는 처리 상태에 반영했다.

구현 근거는 [후속 구현 기록의 ID별 표](../reports/2026-09-18_PIX_RESIDUAL_CORE_IMPLEMENTATION.md#구현과-추적)에 분리했다. 해당 표에 없는 행이나 더 넓은 upstream 옵션을 완료로 승격하지 않는다.

[세부 설계](2026-09-18_PIX_RESIDUAL_DETAILED_DESIGN.md)의 R01–R14가 입력·출력·정의·검증·사용자 샘플을 규정한다. 각 행의 다음 작업은 원래 5범주를 유지한다. 제외/보류/제안 상태의 행은 다음 작업이 표시되어 있어도 자동 착수하지 않는다.

## 처리 상태

| 상태 | 항목 수 |
| --- | ---: |
| 제외 | 9 |
| 채택 | 156 |
| 미판정 | 2 |
| 범위 조정안 | 4 |
| 설명 후 확인 | 2 |
| 부담 조건부 | 1 |
| 착수 보류 | 1 |
| 담당 변경 | 1 |
| 책임 확정 | 1 |
| 합계 | 177 |

숫자는 별개 알고리즘 수나 공수 추정치가 아니다. 기존 평가 판본과 코드·테스트 참조는 아래 각 행에 연결하며, 참조 파일 존재가 동등성 검증 완료를 뜻하지 않는다.

## 전체 배치

| 묶음 | 영역 | 항목 수 |
| --- | --- | ---: |
| R01 | 입출력·mapping·진입점 | 23 |
| R02 | Case 선택·시간·집계 | 14 |
| R03 | Object 분석 단위·관계·변환 | 15 |
| R04 | Case 모델·변환·축약 | 15 |
| R05 | Case 발견 | 14 |
| R06 | Case 적합성 | 10 |
| R07 | OC 모델·발견·적합성·성능 | 12 |
| R08 | Feature·학습·n-gram·검정 | 13 |
| R09 | 자원·조직 | 11 |
| R10 | 시뮬레이션·확률 언어 | 9 |
| R11 | Stream 정정·복구 | 7 |
| R12 | 제약·action·privacy | 5 |
| R13 | 시각화 | 13 |
| R14 | Agent·Schumpeter 경계 | 16 |

## R01 — 입출력·mapping·진입점

### OC-IO-003 · CSV와 별도 객체 속성표의 결합 import

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** CSV의 활동·시각·객체 열을 매핑하고 별도 객체 속성표를 입력할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/io.py](../../src/pix/io.py), [src/pix/tabular/mapping.py](../../src/pix/tabular/mapping.py), [src/pix/tabular/reader.py](../../src/pix/tabular/reader.py)

### OC-IO-004 · OCEL↔dataframe/CSV의 두 표 교환

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCEL object 표현과 dataframe/CSV 표현을 서로 바꿀 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/tabular/reader.py](../../src/pix/tabular/reader.py)

### OC-IO-005 · OCPA OCEL 1 JSON writer

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCPA가 쓰는 OCEL 1 JSON 파일로 다시 출력할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-DATA-033 · CaseLog·record·stream 변환의 보존 계약

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** EventLog·stream·표 형식을 의미 손실을 드러내며 오갈 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/event_log/adapters.py](../../src/pix/event_log/adapters.py), [src/pix/tabular/reader.py](../../src/pix/tabular/reader.py)

### PM-EDGE-012 · PIX 공개 CLI

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 명령행으로 기존 분석 API를 호출하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-IO-002 · XES·gzip XES writer와 metadata 왕복

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** CaseLog를 XES로 내보내 다른 분석 도구에 전달할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/event_log/model.py](../../src/pix/event_log/model.py)

### PM-IO-003 · Enriched OCEL 1 JSON import 확장

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 기본 OCEL 1 JSON을 객체·이벤트 손실을 설명하며 읽는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/ocel/ingest/formats/legacy.py](../../src/pix/ocel/ingest/formats/legacy.py), [src/pix/ocel/ingest/reader.py](../../src/pix/ocel/ingest/reader.py)

### PM-IO-006 · Extended CSV와 별도 객체 CSV import

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** PM4Py의 기존 extended-table CSV와 선택적 객체 CSV를 가져오는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/tabular/mapping.py](../../src/pix/tabular/mapping.py), [src/pix/tabular/reader.py](../../src/pix/tabular/reader.py)

### PM-IO-011 · CSV/Parquet bundle의 실제 환경 실행 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** CSV/Parquet OCEL bundle을 디렉터리 또는 ZIP에서 읽는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/ocel/ingest/formats/_bundle_source.py](../../src/pix/ocel/ingest/formats/_bundle_source.py), [src/pix/ocel/ingest/formats/_bundle_tables.py](../../src/pix/ocel/ingest/formats/_bundle_tables.py), [src/pix/ocel/ingest/formats/bundled.py](../../src/pix/ocel/ingest/formats/bundled.py)

### PM-IO-013 · OCEL 1·enriched·extended CSV·classic SQLite export

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 기존 OCEL 1/PM4Py enriched JSON·XML·CSV·classic SQLite로 내보내는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-IO-014 · Compact CSV·CSV/Parquet bundle writer

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Compact CSV와 CSV/Parquet bundle을 다른 도구에 내보내는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-IO-017 · DFG 파일 형식 reader/writer

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** DFG 모델/구조 파일을 읽고 다시 내보내는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-IO-018 · BPMN 교환의 DI·추가 요소 호환

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** BPMN 모델/구조 파일을 읽고 다시 내보내는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/model_io/__init__.py](../../src/pix/model_io/__init__.py), [src/pix/model_io/bpmn.py](../../src/pix/model_io/bpmn.py), [src/pix/model_io/common.py](../../src/pix/model_io/common.py) / 기존 테스트: [tests/model_io/test_bpmn.py](../../tests/model_io/test_bpmn.py), [tests/model_io/test_pnml.py](../../tests/model_io/test_pnml.py), [tests/model_io/test_ptml.py](../../tests/model_io/test_ptml.py)

### PM-OCEL-030 · 다중 객체형 table→OCEL mapping의 호환 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Case·표 자료를 복수 객체형을 갖는 OCEL로 변환할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/event_log/adapters.py](../../src/pix/event_log/adapters.py), [src/pix/tabular/mapping.py](../../src/pix/tabular/mapping.py), [src/pix/tabular/reader.py](../../src/pix/tabular/reader.py)

### PM-UTIL-001 · 임의 Python predicate 직접 실행 호환

**처리:** 설명 후 확인. 양측 불필요 표 유지. 사용자 함수 직접 실행과 일반 명시 필터를 구분해 설명했으며 확정 범위는 재검토 가능.
**업무 질문:** 사용자가 지정한 조건으로 case·event를 고르고 원본 근거를 유지할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-UTIL-003 · 표 열 mapping의 drop·정렬·시각 변환 대조

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 기존 표의 case·활동·시각 열을 분석 입력으로 명시적으로 연결할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/io.py](../../src/pix/io.py), [src/pix/tabular/mapping.py](../../src/pix/tabular/mapping.py)

### PM-UTIL-004 · Case·활동·시각 열의 참조 keyword API 호환

**처리:** 범위 조정안. 열 선택 기능 필요성과 upstream 인자 호환을 구분. 기존 mapping으로 충분하면 검증만 수행.
**업무 질문:** 어떤 열을 case·활동·시각으로 쓸지 계산 호출에 전달할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/contracts/analysis.py](../../src/pix/contracts/analysis.py), [src/pix/contracts/case_log.py](../../src/pix/contracts/case_log.py)

### PM-UTIL-005 · 복합 classifier의 in-place 변경 호환

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** 복합 classifier를 적용해 활동의 정체성을 정할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/event_log/adapters.py](../../src/pix/event_log/adapters.py)

### PM-UTIL-006 · 임의 타입의 event 속성 sequence 추출

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** case별 특정 이벤트 속성 값을 순서대로 읽을 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/event_log/adapters.py](../../src/pix/event_log/adapters.py)

### PM-UTIL-008 · 활동 문자열로 검산용 CaseLog 생성

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 간단한 활동 문자열로 검산용 로그를 만들 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-UTIL-009 · Process tree 텍스트 parser

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 텍스트로 표현한 process tree를 모델로 읽을 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-UTIL-010 · POWL 텍스트 parser

**처리:** 부담 조건부. 기존 자산 대비 실제 변경 규모 확인 후 비용 조건을 검토. 공수 미측정.
**업무 질문:** 텍스트로 표현한 부분순서 모델을 읽을 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-UTIL-011 · 로그·모델의 bytes 입출력 API 보완

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 로그와 모델을 메모리 내 바이트로 주고받을 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/models.py](../../src/pix/models.py), [src/pix/results.py](../../src/pix/results.py)


## R02 — Case 선택·시간·집계

### PM-DATA-004 · Variant 반복 경로의 PRE/POST·대기·달력 집계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 각 variant의 반복 경로별 소요시간 분포는 어떠한가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-DATA-015 · Process cube의 수치 bin·집계 옵션

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 두 속성 축으로 나눈 process cube의 집계 결과는 무엇인가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-DATA-016 · 활동 전후 PRE/POST 시간·대기 집계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 주어진 활동 전후에 얼마의 시간이 걸리는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-DATA-019 · 분포 계산의 bandwidth·시간대·DST 처리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 숫자 속성·기간의 연속 분포와 시간 단위별 빈도는 어떠한가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-DATA-020 · Performance spectrum의 단절 구간·표본 정책

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 여러 활동을 통과하는 시간 경로의 performance spectrum은 어떠한가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-DATA-023 · 속성 출현 비율·반복 조건 필터 확대

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 이벤트·case 속성 값과 출현 비율에 따라 로그를 선택할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-024 · Variant 빈도·coverage·동률 선택 정책

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 어떤 variant를 남기고 빈도·coverage를 어떻게 제한하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-026 · 시간창의 포함·교차·시작·종료 필터 의미

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 시간창에 포함·교차·시작·종료하는 case 또는 event를 선택할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-027 · Prefix·suffix·비연속 부분열 추출 확장

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 두 활동 사이·prefix·suffix·지정 부분열을 추출할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-028 · 재작업·기간 필터의 속성·business-time 확장

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 길이·기간·재작업 횟수로 case를 선택할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-029 · 경로 지연 필터의 start/complete 시간 기준

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 특정 경로에 너무 오래 걸리는 case를 선택할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-031 · 동률·연속 이벤트 묶기와 case 분할 의미

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 연속·동률 이벤트를 묶거나 활동 발생을 기준으로 case를 분할할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/filtering.py](../../src/pix/case_centric/filtering.py) / 기존 테스트: [tests/case_centric/test_filtering.py](../../tests/case_centric/test_filtering.py)

### PM-DATA-036 · Interval→lifecycle 역변환과 합성 시각 표시

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Lifecycle 이벤트를 실행 interval로 짝짓고 다시 lifecycle로 변환할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/lifecycle.py](../../src/pix/case_centric/lifecycle.py) / 기존 테스트: [tests/case_centric/test_lifecycle.py](../../tests/case_centric/test_lifecycle.py)

### PM-DATA-038 · Case service·sojourn·waiting의 overlap 집계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Case 전체의 service·sojourn·waiting을 집계하여 붙일 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)


## R03 — Object 분석 단위·관계·변환

### OC-DATA-001 · 객체 참여수·속성을 보존하는 CaseLog flattening

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCEL을 객체형별 case log로 투영하고 활동별 객체 수를 얻는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py), [tests/object_centric/test_features.py](../../tests/object_centric/test_features.py)

### OC-DATA-002 · Succinct/exploded 표 정규화·경로 빈도 정리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Succinct/exploded 표를 변환하고 활동·경로 빈도를 정리하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_advanced_filtering.py](../../tests/object_centric/test_advanced_filtering.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py)

### OC-DATA-003 · 여러 OCEL의 ID·schema 충돌 처리 merge

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 여러 OCEL을 합치거나 실행을 표본 선택하고 참조 객체를 정리하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_advanced_filtering.py](../../tests/object_centric/test_advanced_filtering.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py)

### OC-EXEC-004 · Approximate OC variant와 exact 동치의 구분

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 두 실행의 활동·객체 참여 graph가 같은 variant인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/variants.py](../../src/pix/compute/variants.py), [src/pix/object_centric/equivalent_ocel.py](../../src/pix/object_centric/equivalent_ocel.py) / 기존 테스트: [tests/compute/test_variants.py](../../tests/compute/test_variants.py), [tests/object_centric/test_equivalent_ocel.py](../../tests/object_centric/test_equivalent_ocel.py)

### OC-EXEC-005 · OC variant 전수 동형 비교의 정의 대조

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 전수 graph 동형 비교로 실행 variant를 분류할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/variants.py](../../src/pix/compute/variants.py), [src/pix/object_centric/equivalent_ocel.py](../../src/pix/object_centric/equivalent_ocel.py) / 기존 테스트: [tests/compute/test_variants.py](../../tests/compute/test_variants.py), [tests/object_centric/test_equivalent_ocel.py](../../tests/object_centric/test_equivalent_ocel.py)

### OC-FILTER-002 · OC execution의 시작·종료·포함·교차 시간창

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 시간창에 시작·끝·포함·겹침 조건을 만족하는 실행 또는 이벤트만 선택하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/filter_predicates.py](../../src/pix/object_centric/filter_predicates.py), [src/pix/object_centric/filtering.py](../../src/pix/object_centric/filtering.py) / 기존 테스트: [tests/object_centric/test_filter_predicates.py](../../tests/object_centric/test_filter_predicates.py), [tests/object_centric/test_filtering.py](../../tests/object_centric/test_filtering.py), [tests/test_mining_serialization.py](../../tests/test_mining_serialization.py)

### OC-FILTER-005 · 복수 활동 lifecycle 조건 조합

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체 lifecycle에 지정한 활동들이 나타나는 관측만 선택하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/filter_predicates.py](../../src/pix/object_centric/filter_predicates.py), [src/pix/object_centric/filtering.py](../../src/pix/object_centric/filtering.py) / 기존 테스트: [tests/object_centric/test_advanced_filtering.py](../../tests/object_centric/test_advanced_filtering.py), [tests/object_centric/test_filter_predicates.py](../../tests/object_centric/test_filter_predicates.py), [tests/object_centric/test_filtering.py](../../tests/object_centric/test_filtering.py)

### OC-FILTER-006 · EOG·OPERA 성능 filter의 집계 단위

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** EOG 성능 값이 조건에 맞는 이벤트만 선택하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/filter_predicates.py](../../src/pix/object_centric/filter_predicates.py), [src/pix/object_centric/filtering.py](../../src/pix/object_centric/filtering.py) / 기존 테스트: [tests/object_centric/test_advanced_filtering.py](../../tests/object_centric/test_advanced_filtering.py), [tests/object_centric/test_filter_predicates.py](../../tests/object_centric/test_filter_predicates.py), [tests/object_centric/test_filtering.py](../../tests/object_centric/test_filtering.py)

### PM-OCEL-001 · OCEL 속성·객체형·참여수 요약 API

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체형·속성 목록과 활동별 객체 참여 개수는 무엇인가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/constraints.py](../../src/pix/object_centric/constraints.py), [src/pix/object_centric/relations.py](../../src/pix/object_centric/relations.py), [src/pix/object_centric/statistics.py](../../src/pix/object_centric/statistics.py) / 기존 테스트: [tests/object_centric/test_constraints.py](../../tests/object_centric/test_constraints.py), [tests/object_centric/test_relations.py](../../tests/object_centric/test_relations.py), [tests/object_centric/test_statistics.py](../../tests/object_centric/test_statistics.py)

### PM-OCEL-003 · 객체 활동열·기간·상호작용 통합 요약

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체별 관측 활동열·기간·상호작용 객체는 무엇인가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/constraints.py](../../src/pix/object_centric/constraints.py), [src/pix/object_centric/relations.py](../../src/pix/object_centric/relations.py), [src/pix/object_centric/statistics.py](../../src/pix/object_centric/statistics.py) / 기존 테스트: [tests/object_centric/test_constraints.py](../../tests/object_centric/test_constraints.py), [tests/object_centric/test_relations.py](../../tests/object_centric/test_relations.py), [tests/object_centric/test_statistics.py](../../tests/object_centric/test_statistics.py)

### PM-OCEL-004 · 속성을 보존하는 OCEL→CaseLog 투영

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 하나의 객체형을 case로 삼아 OCEL을 펼칠 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py), [tests/object_centric/test_features.py](../../tests/object_centric/test_features.py)

### PM-OCEL-009 · Lifecycle qualifier의 interior·동률·덮어쓰기 정책

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체의 최초·최종 참여를 E2O lifecycle qualifier로 표시할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py), [tests/object_centric/test_features.py](../../tests/object_centric/test_features.py)

### PM-OCEL-012 · 동률 event의 추가 속성 순서와 시각 보존

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 동률 이벤트를 추가 속성으로 정렬하거나 명시적 순서로 처리할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py), [tests/object_centric/test_features.py](../../tests/object_centric/test_features.py)

### PM-OCEL-013 · OCEL 실행 분할·부분 로그의 객체 보존 규칙

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 서로 연결된 객체들 또는 중심 객체의 관련 실행으로 OCEL을 나눌 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/executions.py](../../src/pix/compute/executions.py) / 기존 테스트: [tests/compute/test_executions.py](../../tests/compute/test_executions.py)

### PM-OCEL-031 · OC graph의 통합 NetworkX 반환 호환

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** OCEL의 event/object/직접후속 또는 object feature 관계를 graph로 변환할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/trace.py](../../src/pix/compute/trace.py), [src/pix/object_centric/advanced_filtering.py](../../src/pix/object_centric/advanced_filtering.py), [src/pix/object_centric/enrichment.py](../../src/pix/object_centric/enrichment.py) / 기존 테스트: [tests/compute/test_trace.py](../../tests/compute/test_trace.py), [tests/object_centric/test_enrichment.py](../../tests/object_centric/test_enrichment.py), [tests/object_centric/test_features.py](../../tests/object_centric/test_features.py)


## R04 — Case 모델·변환·축약

### PM-MODEL-002 · 확장 net의 guard·발화·분석 지원 경계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Reset·inhibitor arc와 data guard를 가진 net을 해석할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/decision_mining.py](../../src/pix/case_centric/decision_mining.py), [src/pix/case_centric/discovery.py](../../src/pix/case_centric/discovery.py), [src/pix/case_centric/extended_nets.py](../../src/pix/case_centric/extended_nets.py) / 기존 테스트: [tests/case_centric/test_discovery.py](../../tests/case_centric/test_discovery.py), [tests/case_centric/test_extended_nets.py](../../tests/case_centric/test_extended_nets.py), [tests/case_centric/test_heuristics.py](../../tests/case_centric/test_heuristics.py)

### PM-MODEL-004 · 모델 종류별 미지원 표현·입출력 보완

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Tree·BPMN·POWL·Heuristics net·TS·trie 모델을 식별하고 읽을 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/decision_mining.py](../../src/pix/case_centric/decision_mining.py), [src/pix/case_centric/discovery.py](../../src/pix/case_centric/discovery.py), [src/pix/case_centric/heuristics.py](../../src/pix/case_centric/heuristics.py) / 기존 테스트: [tests/case_centric/test_discovery.py](../../tests/case_centric/test_discovery.py), [tests/case_centric/test_heuristics.py](../../tests/case_centric/test_heuristics.py), [tests/case_centric/test_model_labels.py](../../tests/case_centric/test_model_labels.py)

### PM-MODEL-007 · BPMN→PN의 추가 gateway·event 의미

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** BPMN을 Petri net으로 변환하여 계산할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/_mining_registry.py](../../src/pix/_mining_registry.py), [src/pix/case_centric/bpmn_conversion.py](../../src/pix/case_centric/bpmn_conversion.py), [src/pix/case_centric/dfg_conversion.py](../../src/pix/case_centric/dfg_conversion.py) / 기존 테스트: [tests/case_centric/test_bpmn_conversion.py](../../tests/case_centric/test_bpmn_conversion.py), [tests/case_centric/test_dfg_conversion.py](../../tests/case_centric/test_dfg_conversion.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-MODEL-008 · WF net→tree/BPMN의 지원 구조 확대·거부 근거

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Workflow net을 process tree 또는 BPMN으로 변환할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/_mining_registry.py](../../src/pix/_mining_registry.py), [src/pix/case_centric/bpmn_conversion.py](../../src/pix/case_centric/bpmn_conversion.py), [src/pix/case_centric/dfg_conversion.py](../../src/pix/case_centric/dfg_conversion.py) / 기존 테스트: [tests/case_centric/test_bpmn_conversion.py](../../tests/case_centric/test_bpmn_conversion.py), [tests/case_centric/test_dfg_conversion.py](../../tests/case_centric/test_dfg_conversion.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-MODEL-009 · PN/BPMN→POWL의 변환 가능 조건

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Petri net 또는 BPMN을 POWL로 변환할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/_mining_registry.py](../../src/pix/_mining_registry.py), [src/pix/case_centric/bpmn_conversion.py](../../src/pix/case_centric/bpmn_conversion.py), [src/pix/case_centric/dfg_conversion.py](../../src/pix/case_centric/dfg_conversion.py) / 기존 테스트: [tests/case_centric/test_bpmn_conversion.py](../../tests/case_centric/test_bpmn_conversion.py), [tests/case_centric/test_dfg_conversion.py](../../tests/case_centric/test_dfg_conversion.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-MODEL-010 · 비직렬·병렬 POWL의 tree 변환 강제 확장

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** POWL을 net 또는 tree로 바꾸면 어떤 행동이 보존되는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/_mining_registry.py](../../src/pix/_mining_registry.py), [src/pix/case_centric/bpmn_conversion.py](../../src/pix/case_centric/bpmn_conversion.py), [src/pix/case_centric/dfg_conversion.py](../../src/pix/case_centric/dfg_conversion.py) / 기존 테스트: [tests/case_centric/test_bpmn_conversion.py](../../tests/case_centric/test_bpmn_conversion.py), [tests/case_centric/test_dfg_conversion.py](../../tests/case_centric/test_dfg_conversion.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-MODEL-011 · GeneticMatrix→PN의 잔여 호환 변환

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** Heuristics net·GeneticMatrix·trie를 Petri net으로 변환할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/_mining_registry.py](../../src/pix/_mining_registry.py), [src/pix/case_centric/bpmn_conversion.py](../../src/pix/case_centric/bpmn_conversion.py), [src/pix/case_centric/dfg_conversion.py](../../src/pix/case_centric/dfg_conversion.py) / 기존 테스트: [tests/case_centric/test_bpmn_conversion.py](../../tests/case_centric/test_bpmn_conversion.py), [tests/case_centric/test_dfg_conversion.py](../../tests/case_centric/test_dfg_conversion.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-MODEL-015 · Workflow soundness의 liveness·진단 범위 확대

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Workflow net은 종료 가능성·dead transition·boundedness 등 soundness를 만족하는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/_model_algebra.py](../../src/pix/case_centric/_model_algebra.py), [src/pix/case_centric/coverability.py](../../src/pix/case_centric/coverability.py), [src/pix/case_centric/model_analysis.py](../../src/pix/case_centric/model_analysis.py) / 기존 테스트: [tests/case_centric/test_coverability.py](../../tests/case_centric/test_coverability.py), [tests/case_centric/test_model_algebra.py](../../tests/case_centric/test_model_algebra.py), [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py)

### PM-MODEL-016 · Marking equation 하한의 정당성·solver 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Marking equation으로 도달 비용 하한을 계산할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/_equation_solver.py](../../src/pix/case_centric/_equation_solver.py), [src/pix/case_centric/_model_algebra.py](../../src/pix/case_centric/_model_algebra.py), [src/pix/case_centric/alignment_search.py](../../src/pix/case_centric/alignment_search.py) / 기존 테스트: [tests/case_centric/test_equation_solver.py](../../tests/case_centric/test_equation_solver.py), [tests/case_centric/test_model_algebra.py](../../tests/case_centric/test_model_algebra.py), [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py)

### PM-MODEL-017 · Extended marking equation의 split·하한 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Split point를 가진 extended marking equation 하한은 얼마인가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/_equation_solver.py](../../src/pix/case_centric/_equation_solver.py), [src/pix/case_centric/_model_algebra.py](../../src/pix/case_centric/_model_algebra.py), [src/pix/case_centric/alignment_search.py](../../src/pix/case_centric/alignment_search.py) / 기존 테스트: [tests/case_centric/test_equation_solver.py](../../tests/case_centric/test_equation_solver.py), [tests/case_centric/test_model_algebra.py](../../tests/case_centric/test_model_algebra.py), [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py)

### PM-MODEL-018 · Synchronous product의 비용·identity·저장 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Trace와 모델의 synchronous product를 구성할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/alignment_search.py](../../src/pix/case_centric/alignment_search.py), [src/pix/case_centric/marking_equation.py](../../src/pix/case_centric/marking_equation.py), [src/pix/compute/conformance.py](../../src/pix/compute/conformance.py) / 기존 테스트: [tests/case_centric/test_alignment_search.py](../../tests/case_centric/test_alignment_search.py), [tests/test_marking_equation.py](../../tests/test_marking_equation.py)

### PM-MODEL-019 · 최대 모델 분해의 가중 arc·merge 지원 범위

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 모델을 최대 구성요소로 분해하고 다시 조합할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/decomposed_alignment.py](../../src/pix/case_centric/decomposed_alignment.py), [src/pix/case_centric/maximal_decomposition.py](../../src/pix/case_centric/maximal_decomposition.py), [src/pix/case_centric/model_analysis.py](../../src/pix/case_centric/model_analysis.py) / 기존 테스트: [tests/case_centric/test_decomposed_alignment.py](../../tests/case_centric/test_decomposed_alignment.py), [tests/case_centric/test_maximal_decomposition.py](../../tests/case_centric/test_maximal_decomposition.py), [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py)

### PM-MODEL-020 · Invisible·implicit place·Murata 축약 규칙 확대

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 불필요한 invisible 구조나 implicit place를 의미를 보존하며 제거할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/_mining_registry.py](../../src/pix/_mining_registry.py), [src/pix/case_centric/model_analysis.py](../../src/pix/case_centric/model_analysis.py), [src/pix/case_centric/tree_reduction.py](../../src/pix/case_centric/tree_reduction.py) / 기존 테스트: [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py), [tests/case_centric/test_tree_reduction.py](../../tests/case_centric/test_tree_reduction.py)

### PM-MODEL-022 · 모델 행동·구조 유사도의 지표 구분

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 두 모델이 행동·구조 관점에서 얼마나 비슷한가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/model_analysis.py](../../src/pix/case_centric/model_analysis.py) / 기존 테스트: [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py)

### PM-MODEL-023 · Label 의미 매칭·모델 embedding 유사도

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 모델 embedding 또는 label 의미로 유사도와 label 매핑을 구할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/model_analysis.py](../../src/pix/case_centric/model_analysis.py) / 기존 테스트: [tests/case_centric/test_model_analysis.py](../../tests/case_centric/test_model_analysis.py)


## R05 — Case 발견

### PM-DISC-006 · Heuristics Miner의 AND·loop·threshold 의미 정리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Dependency와 AND threshold로 잡음을 제어한 Heuristics net은 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/heuristics.py](../../src/pix/case_centric/heuristics.py), [src/pix/case_centric/heuristics_conversion.py](../../src/pix/case_centric/heuristics_conversion.py) / 기존 테스트: [tests/case_centric/test_heuristics.py](../../tests/case_centric/test_heuristics.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-DISC-007 · Heuristics++의 시간·동시성 발견 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Heuristics++의 빈도·성능·동시성 정의에 따른 발견 결과는 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/heuristics.py](../../src/pix/case_centric/heuristics.py), [src/pix/case_centric/heuristics_conversion.py](../../src/pix/case_centric/heuristics_conversion.py) / 기존 테스트: [tests/case_centric/test_heuristics.py](../../tests/case_centric/test_heuristics.py), [tests/case_centric/test_heuristics_conversion.py](../../tests/case_centric/test_heuristics_conversion.py)

### PM-DISC-008 · Region/ILP 발견의 solver·탐색 지원 범위

**처리:** 착수 보류. 공동 학습·설계 전 구현하지 않음. 기존 지원은 유지.
**업무 질문:** Trace를 설명하는 region 기반 ILP 모델은 무엇인가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/extended_discovery.py](../../src/pix/case_centric/extended_discovery.py) / 기존 테스트: [tests/case_centric/test_extended_discovery.py](../../tests/case_centric/test_extended_discovery.py)

### PM-DISC-009 · Genetic Miner의 참조 genotype·평가함수 확장

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** 후보 모델을 진화시키며 fitness 기반으로 선택한 모델은 무엇인가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/genetic_miner.py](../../src/pix/case_centric/genetic_miner.py) / 기존 테스트: [tests/case_centric/test_genetic_miner.py](../../tests/case_centric/test_genetic_miner.py)

### PM-DISC-010 · POWL 발견의 추가 variant와 부분순서 기준

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 부분순서를 표현하는 POWL 모델은 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/powl.py](../../src/pix/case_centric/powl.py) / 기존 테스트: [tests/case_centric/test_powl.py](../../tests/case_centric/test_powl.py)

### PM-DISC-011 · Classic Split Miner의 OR-join·추가 구조 지원

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 빈도 필터와 동시성 판단에서 classic Split Miner BPMN을 발견할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/split_miner.py](../../src/pix/case_centric/split_miner.py) / 기존 테스트: [tests/case_centric/test_split_miner.py](../../tests/case_centric/test_split_miner.py)

### PM-DISC-012 · Split Miner 2의 lifecycle 동시성·동명 활동 처리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Lifecycle 구간 겹침을 활용한 Split Miner 2 BPMN은 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/split_miner.py](../../src/pix/case_centric/split_miner.py) / 기존 테스트: [tests/case_centric/test_split_miner.py](../../tests/case_centric/test_split_miner.py)

### PM-DISC-013 · IM→BPMN 변환 경로의 의미 보존 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Inductive Miner 결과를 BPMN으로 제공할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/inductive.py](../../src/pix/case_centric/inductive.py), [src/pix/case_centric/model_conversion.py](../../src/pix/case_centric/model_conversion.py) / 기존 테스트: [tests/case_centric/test_inductive.py](../../tests/case_centric/test_inductive.py), [tests/case_centric/test_model_conversion.py](../../tests/case_centric/test_model_conversion.py)

### PM-DISC-014 · POWL·DFG의 추가 footprint 추출

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 로그 또는 모델에서 순서·병렬·시작·종료 footprints를 추출할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/discovery.py](../../src/pix/case_centric/discovery.py), [src/pix/case_centric/model_discovery.py](../../src/pix/case_centric/model_discovery.py) / 기존 테스트: [tests/case_centric/test_discovery.py](../../tests/case_centric/test_discovery.py), [tests/case_centric/test_model_discovery.py](../../tests/case_centric/test_model_discovery.py)

### PM-DISC-015 · DFG→Alpha/Heuristics causal 관계 API

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** DFG에서 Alpha 또는 Heuristics 방식의 causal 관계를 얻을 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/alpha.py](../../src/pix/case_centric/alpha.py) / 기존 테스트: [tests/case_centric/test_alpha.py](../../tests/case_centric/test_alpha.py)

### PM-DISC-022 · Case ID가 없는 로그의 흐름 추정 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Case 식별이 불충분한 이벤트로부터 활동 간 흐름을 추정할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/correlation.py](../../src/pix/case_centric/correlation.py) / 기존 테스트: [tests/test_correlation.py](../../tests/test_correlation.py)

### PM-DISC-023 · Local Process Model의 후보·품질·탐색 한도

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 전체 모델 대신 자주 반복되는 국소 프로세스 모델과 품질을 찾을 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/discovery.py](../../src/pix/case_centric/discovery.py) / 기존 테스트: [tests/case_centric/test_discovery.py](../../tests/case_centric/test_discovery.py)

### PM-DISC-025 · Performance DFG의 독립 결과·집계·달력

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 직접 후속 관계의 소요시간 분포를 계산할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-DISC-026 · 활동 삼중항·edge 속성 분포의 경계 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 활동 삼중항과 edge별 case 속성 분포를 계산할 수 있는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/context_discovery.py](../../src/pix/case_centric/context_discovery.py) / 기존 테스트: [tests/case_centric/test_context_discovery.py](../../tests/case_centric/test_context_discovery.py)


## R06 — Case 적합성

### PM-CONF-002 · Backward silent replay의 탐색·보정 정책

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Backward silent 탐색을 사용하는 token replay 결과는 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/backwards_replay.py](../../src/pix/case_centric/backwards_replay.py) / 기존 테스트: [tests/case_centric/test_backwards_replay.py](../../tests/case_centric/test_backwards_replay.py)

### PM-CONF-003 · 최소비용 PN alignment의 비용·동률·종료 대조

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Trace와 accepting Petri net 사이의 최소 비용 alignment는 무엇인가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/alignment_search.py](../../src/pix/case_centric/alignment_search.py), [src/pix/compute/conformance.py](../../src/pix/compute/conformance.py) / 기존 테스트: [tests/case_centric/test_alignment_search.py](../../tests/case_centric/test_alignment_search.py)

### PM-CONF-004 · Discounted alignment의 참조 목적함수 호환

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** Discounted edit 비용을 쓰는 Petri net alignment는 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/alignment_search.py](../../src/pix/case_centric/alignment_search.py) / 기존 테스트: [tests/case_centric/test_alignment_search.py](../../tests/case_centric/test_alignment_search.py)

### PM-CONF-005 · 근사 alignment의 오차·상하한·완료 범위

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 큰 trace에서 근사 alignment를 계산하고 오차·완료 범위를 설명할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/_fixed_horizon_alignment.py](../../src/pix/case_centric/_fixed_horizon_alignment.py), [src/pix/case_centric/approximate_alignment.py](../../src/pix/case_centric/approximate_alignment.py) / 기존 테스트: [tests/case_centric/test_approximate_alignment.py](../../tests/case_centric/test_approximate_alignment.py)

### PM-CONF-006 · 공유 전이를 가진 분해 alignment 재조합

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 분해한 Petri net을 조합해 alignment를 구할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/decomposed_alignment.py](../../src/pix/case_centric/decomposed_alignment.py) / 기존 테스트: [tests/case_centric/test_decomposed_alignment.py](../../tests/case_centric/test_decomposed_alignment.py)

### PM-CONF-007 · Process tree alignment의 정확·근사 경로 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Process tree 자체에 대한 정확·근사 alignment는 무엇인가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/tree_alignment.py](../../src/pix/case_centric/tree_alignment.py) / 기존 테스트: [tests/case_centric/test_tree_alignment.py](../../tests/case_centric/test_tree_alignment.py)

### PM-CONF-010 · 대표 variant conformance의 가중치·집계 경계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 대표 variant 부분집합으로 conformance를 근사하고 집계 경계를 줄 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/conformance_approximation.py](../../src/pix/case_centric/conformance_approximation.py) / 기존 테스트: [tests/case_centric/test_conformance_approximation.py](../../tests/case_centric/test_conformance_approximation.py)

### PM-CONF-011 · Anti-alignment precision의 목적·정규화

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 로그에서 가장 멀리 떨어진 허용 행동과 anti-alignment precision은 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/pn_language_alignment.py](../../src/pix/case_centric/pn_language_alignment.py) / 기존 테스트: [tests/case_centric/test_pn_language_alignment.py](../../tests/case_centric/test_pn_language_alignment.py)

### PM-CONF-012 · Multi-alignment의 참조 sum/minimax 목적 확장

**처리:** 범위 조정안. 총거리/최대거리 대표 실행을 비교하는 설계안. 사용자 필요 표는 있으나 목적 정의는 검토 대상.
**업무 질문:** 여러 trace를 대표하도록 최대 거리를 줄이는 모델 행동은 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/pn_language_alignment.py](../../src/pix/case_centric/pn_language_alignment.py) / 기존 테스트: [tests/case_centric/test_pn_language_alignment.py](../../tests/case_centric/test_pn_language_alignment.py)

### PM-CONF-024 · 단일 trace 적합성 판정의 공통 API

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 단일 trace가 tree 또는 Petri net에 적합한지 판정할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/conformance.py](../../src/pix/case_centric/conformance.py) / 기존 테스트: [tests/case_centric/test_conformance.py](../../tests/case_centric/test_conformance.py)


## R07 — OC 모델·발견·적합성·성능

### OC-CONF-004 · Object context fitness/precision의 참여·분모

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체별 과거 context에서 로그와 모델의 가능한 다음 활동이 얼마나 일치하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/object_context.py](../../src/pix/compute/object_context.py) / 기존 테스트: [tests/compute/test_object_context.py](../../tests/compute/test_object_context.py), [tests/compute/test_object_context_oracle.py](../../tests/compute/test_object_context_oracle.py)

### OC-CONF-005 · OC replay backward search·cache·flooding 정책

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Silent transition 경로와 token flooding을 replay에서 어떤 정책으로 다루는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/conformance.py](../../src/pix/object_centric/conformance.py) / 기존 테스트: [tests/object_centric/test_conformance.py](../../tests/object_centric/test_conformance.py)

### OC-DISC-001 · OCPA 계열 OCPN 발견의 variable arc·필터

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체별 관측 흐름을 통합해 공동 참여와 variable arc를 가진 OCPN을 찾는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/ocpn_discovery.py](../../src/pix/compute/ocpn_discovery.py), [src/pix/object_centric/legacy_discovery.py](../../src/pix/object_centric/legacy_discovery.py), [src/pix/object_centric/model_integration.py](../../src/pix/object_centric/model_integration.py) / 기존 테스트: [tests/compute/test_ocpn_discovery.py](../../tests/compute/test_ocpn_discovery.py), [tests/object_centric/test_legacy_discovery.py](../../tests/object_centric/test_legacy_discovery.py), [tests/object_centric/test_model_integration.py](../../tests/object_centric/test_model_integration.py)

### OC-MODEL-001 · OCPN의 가중 arc·유한 객체 계약 확장

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCPN place·transition·arc·marking과 변경을 표현하고 저장할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/model_labels.py](../../src/pix/case_centric/model_labels.py), [src/pix/compute/model_semantics.py](../../src/pix/compute/model_semantics.py), [src/pix/compute/object_bindings.py](../../src/pix/compute/object_bindings.py) / 기존 테스트: [tests/case_centric/test_model_labels.py](../../tests/case_centric/test_model_labels.py), [tests/compute/test_object_bindings.py](../../tests/compute/test_object_bindings.py), [tests/object_centric/test_model_integration.py](../../tests/object_centric/test_model_integration.py)

### OC-MODEL-004 · OCPA Murata 잔여 축약 규칙

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 보존 조건 아래 OCPN의 불필요한 place·transition을 줄일 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/model_integration.py](../../src/pix/object_centric/model_integration.py), [src/pix/object_centric/models.py](../../src/pix/object_centric/models.py), [src/pix/object_centric/subprocess.py](../../src/pix/object_centric/subprocess.py) / 기존 테스트: [tests/object_centric/test_model_integration.py](../../tests/object_centric/test_model_integration.py), [tests/object_centric/test_models.py](../../tests/object_centric/test_models.py), [tests/object_centric/test_subprocess.py](../../tests/object_centric/test_subprocess.py)

### OC-PERF-005 · OPERA activity/object/arc 집계·annotation 확대

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 모델 activity·arc 빈도와 객체 참여/fitness 진단을 어떻게 집계·annotation하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/model_integration.py](../../src/pix/object_centric/model_integration.py), [src/pix/object_centric/performance.py](../../src/pix/object_centric/performance.py) / 기존 테스트: [tests/object_centric/test_model_integration.py](../../tests/object_centric/test_model_integration.py), [tests/object_centric/test_performance.py](../../tests/object_centric/test_performance.py)

### OC-PERF-006 · OC 성능 중앙값·표준편차 등 추가 통계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 성능 표본을 평균·중앙값·표준편차·합·최소·최대로 요약하면 어떤 값인가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/performance.py](../../src/pix/object_centric/performance.py) / 기존 테스트: [tests/object_centric/test_performance.py](../../tests/object_centric/test_performance.py)

### PM-MODEL-026 · OCPN의 가중치·cardinality·객체 발화 경계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체 token과 variable arc를 가진 OCPN을 구성하고 발화할 수 있는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/model_semantics.py](../../src/pix/compute/model_semantics.py), [src/pix/compute/object_bindings.py](../../src/pix/compute/object_bindings.py), [src/pix/object_centric/model_integration.py](../../src/pix/object_centric/model_integration.py) / 기존 테스트: [tests/compute/test_object_bindings.py](../../tests/compute/test_object_bindings.py), [tests/object_centric/test_model_integration.py](../../tests/object_centric/test_model_integration.py)

### PM-MODEL-027 · OCCausalNet→OCPN 변환의 제약 보존

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCCausalNet을 OCPN으로 변환하면 어떤 제약이 유지되거나 손실되는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/models.py](../../src/pix/object_centric/models.py) / 기존 테스트: [tests/object_centric/test_models.py](../../tests/object_centric/test_models.py)

### PM-MODEL-028 · OCPN→marker causal net의 객체 흐름 의미

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCPN의 객체 흐름을 marker 기반 causal net으로 표현할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/models.py](../../src/pix/object_centric/models.py) / 기존 테스트: [tests/object_centric/test_models.py](../../tests/object_centric/test_models.py)

### PM-OCEL-006 · PM4Py 계열 OCPN 발견의 variable arc·필터 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체형별 net을 결합한 OCPN을 발견할 수 있는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/compute/ocpn_discovery.py](../../src/pix/compute/ocpn_discovery.py), [src/pix/object_centric/legacy_discovery.py](../../src/pix/object_centric/legacy_discovery.py), [src/pix/object_centric/model_integration.py](../../src/pix/object_centric/model_integration.py) / 기존 테스트: [tests/compute/test_ocpn_discovery.py](../../tests/compute/test_ocpn_discovery.py), [tests/object_centric/test_legacy_discovery.py](../../tests/object_centric/test_legacy_discovery.py), [tests/object_centric/test_model_integration.py](../../tests/object_centric/test_model_integration.py)

### PM-OCEL-024 · ET-OT·OTG 기준 graph의 빈도 적합성 지표

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 실제 ET-OT·OTG와 기준 graph의 관계·빈도 차이는 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/graph_comparison.py](../../src/pix/object_centric/graph_comparison.py), [src/pix/object_centric/relations.py](../../src/pix/object_centric/relations.py) / 기존 테스트: [tests/object_centric/test_graph_comparison.py](../../tests/object_centric/test_graph_comparison.py), [tests/object_centric/test_relations.py](../../tests/object_centric/test_relations.py)


## R08 — Feature·학습·n-gram·검정

### PM-ADV-001 · 학습/검증 분할의 추가 전략·층화

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 전체 case를 보존하면서 학습·검증 집합을 나누는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/feature_dataset.py](../../src/pix/case_centric/feature_dataset.py), [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_feature_dataset.py](../../tests/case_centric/test_feature_dataset.py), [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-003 · Case 결과·처리·대기·도착 feature 표

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 전체 case의 결과와 처리·대기·도착 정보를 학습 표에 붙이는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/feature_dataset.py](../../src/pix/case_centric/feature_dataset.py), [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_feature_dataset.py](../../tests/case_centric/test_feature_dataset.py), [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-004 · Case engineered feature의 추가 속성·시간 항목

**처리:** 미판정. case 요약 feature의 추가 확장만 선택 설계. 답변 전 착수하지 않음.
**업무 질문:** Case 하나를 활동·속성·시간 등의 수치 feature 벡터로 표현하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/feature_dataset.py](../../src/pix/case_centric/feature_dataset.py), [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_feature_dataset.py](../../tests/case_centric/test_feature_dataset.py), [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-005 · Event sequence tensor의 추가 feature schema

**처리:** 미판정. 기존 sequence tensor 유지. 추가 schema는 답변 전 착수하지 않음.
**업무 질문:** Case 안의 각 이벤트를 순서가 유지된 feature 벡터로 표현하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/feature_dataset.py](../../src/pix/case_centric/feature_dataset.py), [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_feature_dataset.py](../../tests/case_centric/test_feature_dataset.py), [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-006 · Temporal feature의 달력 bucket·lazy 실행

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 시간 구간별 프로세스 feature와 변화 시계열을 만드는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-007 · 복합 속성·trace 문맥의 n-gram 인코딩

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 활동 토큰과 n-gram을 count·binary·TF-IDF 형태로 인코딩하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-008 · Word2Vec·Doc2Vec의 학습 품질·옵션 검증

**처리:** 범위 조정안. Word2Vec/Doc2Vec 추가 고도화 보류안. 외부 embedding 및 표현 품질 비교는 별도 요구로 검토.
**업무 질문:** Trace를 학습된 Word2Vec·Doc2Vec 벡터로 표현하는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/embeddings.py](../../src/pix/case_centric/embeddings.py), [src/pix/case_centric/transformer_embeddings.py](../../src/pix/case_centric/transformer_embeddings.py) / 기존 테스트: [tests/case_centric/test_embeddings.py](../../tests/case_centric/test_embeddings.py), [tests/case_centric/test_transformer_embeddings.py](../../tests/case_centric/test_transformer_embeddings.py)

### PM-ADV-009 · Transformer checkpoint의 실제 추론 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Case·event 문맥을 transformer embedding으로 표현하는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/embeddings.py](../../src/pix/case_centric/embeddings.py), [src/pix/case_centric/transformer_embeddings.py](../../src/pix/case_centric/transformer_embeddings.py) / 기존 테스트: [tests/case_centric/test_embeddings.py](../../tests/case_centric/test_embeddings.py), [tests/case_centric/test_transformer_embeddings.py](../../tests/case_centric/test_transformer_embeddings.py)

### PM-ADV-010 · 전이·place 좌표별 replay/alignment feature

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Alignment와 token replay 진단을 학습 feature로 바꾸는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/features.py](../../src/pix/case_centric/features.py) / 기존 테스트: [tests/case_centric/test_features.py](../../tests/case_centric/test_features.py)

### PM-ADV-013 · 분기 직전 categorical feature 자동 추출

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 분기 직전 어떤 데이터가 경로 선택과 연관되는지 설명하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/advanced.py](../../src/pix/case_centric/advanced.py), [src/pix/case_centric/decision_evaluation.py](../../src/pix/case_centric/decision_evaluation.py), [src/pix/case_centric/decision_mining.py](../../src/pix/case_centric/decision_mining.py) / 기존 테스트: [tests/case_centric/test_advanced.py](../../tests/case_centric/test_advanced.py), [tests/case_centric/test_decision_evaluation.py](../../tests/case_centric/test_decision_evaluation.py), [tests/test_decision_mining.py](../../tests/test_decision_mining.py)

### PM-ADV-014 · Case clustering의 scaling·초기화·안정성 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Case feature profile로 유사한 사례를 군집화하는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/advanced.py](../../src/pix/case_centric/advanced.py) / 기존 테스트: [tests/case_centric/test_advanced.py](../../tests/case_centric/test_advanced.py)

### PM-ADV-015 · 하위 로그 군집의 행동 거리·가중치 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Trace 속성별 하위 로그를 행동 거리로 군집화하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/advanced.py](../../src/pix/case_centric/advanced.py) / 기존 테스트: [tests/case_centric/test_advanced.py](../../tests/case_centric/test_advanced.py)

### PM-ADV-016 · Drift 검정의 검출력·의존성·오탐 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 시간에 따라 프로세스 관계 분포가 바뀌는 구간을 찾는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/advanced.py](../../src/pix/case_centric/advanced.py), [src/pix/case_centric/drift_evaluation.py](../../src/pix/case_centric/drift_evaluation.py) / 기존 테스트: [tests/case_centric/test_advanced.py](../../tests/case_centric/test_advanced.py), [tests/case_centric/test_drift_evaluation.py](../../tests/case_centric/test_drift_evaluation.py)


## R09 — 자원·조직

### PM-ORG-001 · 업무 인계 network의 분모·순서 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 누가 누구에게 업무를 인계하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-002 · 공동 작업 network의 case·쌍 가중치

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 같은 case에서 어떤 자원들이 함께 일하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-003 · Subcontracting의 반복 반환 구간 집계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 업무를 맡겼다가 돌아오는 subcontracting 관계는 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-004 · 자원 유사도의 0·퇴화 벡터 처리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 활동 구성을 기준으로 어떤 자원이 유사한가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-005 · 조직 역할 발견의 실제 규모·안정성 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 활동 집합을 수행하는 조직 역할을 발견하는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-006 · 속성 인계 network의 추가 타입·시간대 지원

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 선택한 속성의 인계 network 빈도·시간을 분석하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-007 · Focus·stake·coverage·기여도 분모

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 발견한 조직 집단의 focus·stake·coverage·기여를 진단하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-008 · 자원 기여도와 업무 완료의 구분

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 자원별 활동 종류·빈도·완료 case와 기여 비율은 얼마인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-009 · Workload·multitasking의 interval·중복 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 자원의 평균 workload와 multitasking 정도는 얼마인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-010 · 자원 소요시간의 lifecycle·결측 처리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 자원이 수행한 활동·case의 평균 소요시간은 얼마인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)

### PM-ORG-011 · 사회적 위치·공동 참여 지표의 범위

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 자원 간 공동 참여와 사회적 위치를 수치화하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/organization.py](../../src/pix/case_centric/organization.py) / 기존 테스트: [tests/case_centric/test_organization.py](../../tests/case_centric/test_organization.py)


## R10 — 시뮬레이션·확률 언어

### PM-ADV-017 · 확률 언어 거리의 무한·절단 모델 처리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 두 로그·모델의 확률적 trace 언어가 얼마나 다른가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/advanced.py](../../src/pix/case_centric/advanced.py) / 기존 테스트: [tests/case_centric/test_advanced.py](../../tests/case_centric/test_advanced.py)

### PM-DATA-005 · Trace 확률 언어의 유한·표본·무한 범위

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 관측 로그 또는 모델의 trace 확률 언어는 무엇인가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/statistics.py](../../src/pix/case_centric/statistics.py) / 기존 테스트: [tests/case_centric/test_statistics.py](../../tests/case_centric/test_statistics.py)

### PM-SIM-001 · PN playout의 실행·열거·종료 한도

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Petri net이 허용하는 유한 실행을 생성·열거하는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py) / 기존 테스트: [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py)

### PM-SIM-002 · 로그 기반 stochastic map·종료 정책

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 확률과 시간 분포를 가진 Petri net 실행을 생성하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/resource_simulation.py](../../src/pix/case_centric/resource_simulation.py), [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py), [src/pix/case_centric/timed_playout.py](../../src/pix/case_centric/timed_playout.py) / 기존 테스트: [tests/case_centric/test_resource_simulation.py](../../tests/case_centric/test_resource_simulation.py), [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py), [tests/case_centric/test_timed_playout.py](../../tests/case_centric/test_timed_playout.py)

### PM-SIM-003 · Tree playout 방식별 언어·표본 편향 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Process tree로부터 무작위·전체·top-bottom 실행을 생성하는가?
**다음 작업:** 기존 경로 재현 → 독립 oracle·실환경 검증 → 실패한 부분만 수정 → 실행 증거 기록.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py) / 기존 테스트: [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py)

### PM-SIM-004 · DFG 실행 열거의 경로 확률·종료 의미

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** DFG의 시작·끝·전이 빈도로 실행을 생성하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py) / 기존 테스트: [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py)

### PM-SIM-005 · DFG 시간 playout의 duration·결측 정의

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** DFG 경로에 성능 시간을 붙여 실행을 생성하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py) / 기존 테스트: [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py)

### PM-SIM-009 · PN 동시 실행과 자원·queue의 통합 simulation

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 자원 제약과 queue 아래에서 처리·대기 결과를 simulation하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/resource_simulation.py](../../src/pix/case_centric/resource_simulation.py), [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py) / 기존 테스트: [tests/case_centric/test_resource_simulation.py](../../tests/case_centric/test_resource_simulation.py), [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py)

### PM-SIM-010 · 합성 process tree의 추가 분포·참조 옵션

**처리:** 범위 조정안. 인공 tree 참조 옵션과 관측 Agent 분포 추정·비교를 분리. 후자는 제안 범위로 설계.
**업무 질문:** 설정한 크기와 operator 비율의 인공 process tree를 생성하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/simulation.py](../../src/pix/case_centric/simulation.py) / 기존 테스트: [tests/case_centric/test_simulation.py](../../tests/case_centric/test_simulation.py)


## R11 — Stream 정정·복구

### PM-STREAM-002 · XES/CSV 공개 event·trace iterator

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** XES·CSV를 이벤트·trace 단위 iterator로 공급하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-STREAM-004 · DFG 정정 처리의 전용 증분·기억량 최적화

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 새 이벤트가 오면 DFG 빈도와 시작·끝을 갱신하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/revisable_stream.py](../../src/pix/case_centric/revisable_stream.py), [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py) / 기존 테스트: [tests/case_centric/test_revisable_stream.py](../../tests/case_centric/test_revisable_stream.py), [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py)

### PM-STREAM-005 · Streaming token replay의 정정·재처리

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Petri net token replay 상태를 이벤트마다 갱신하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py) / 기존 테스트: [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py)

### PM-STREAM-006 · Streaming temporal profile의 정정·열린 관측

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 진행 중 실행의 temporal profile 위반을 갱신하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py) / 기존 테스트: [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py)

### PM-STREAM-007 · Streaming Declare의 정정·재생

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 진행 중 실행의 Declare automaton 상태를 갱신하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py) / 기존 테스트: [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py)

### PM-STREAM-008 · Streaming footprint의 정정 반영

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 진행 중 실행이 허용된 footprint 관계를 따르는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py) / 기존 테스트: [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py)

### PM-STREAM-009 · Online alignment의 기억·look-ahead·오차 경계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 제한된 기억과 look-ahead로 online alignment를 근사하는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/online_alignment.py](../../src/pix/case_centric/online_alignment.py), [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py) / 기존 테스트: [tests/case_centric/test_online_alignment.py](../../tests/case_centric/test_online_alignment.py), [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py)


## R12 — 제약·action·privacy

### OC-ACT-003 · Action 구조 영향의 방향·객체형 범위

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Action이 구조상 전후 활동과 객체형에 미치는 영향 범위는 무엇인가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/actions.py](../../src/pix/object_centric/actions.py) / 기존 테스트: [tests/object_centric/test_actions.py](../../tests/object_centric/test_actions.py)

### OC-ACT-005 · Action 전후 성능 비교의 cohort·인과 경계

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Action 전후 관측창에서 활동·객체 성능이 얼마나 달라졌는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/actions.py](../../src/pix/object_centric/actions.py) / 기존 테스트: [tests/object_centric/test_actions.py](../../tests/object_centric/test_actions.py)

### OC-RULE-008 · 데이터 기반 constraint graph 발견

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Constraint graph 구조를 데이터에서 만들고 규칙 근거로 연결할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/object_centric/constraints.py](../../src/pix/object_centric/constraints.py) / 기존 테스트: [tests/object_centric/test_constraints.py](../../tests/object_centric/test_constraints.py)

### PM-ADV-019 · SACOFA 익명화의 공개 가능 범위·보장 검증

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 제어흐름 variant 빈도를 privacy 정의에 따라 익명화하는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/privacy.py](../../src/pix/case_centric/privacy.py), [src/pix/case_centric/sacofa.py](../../src/pix/case_centric/sacofa.py) / 기존 테스트: [tests/case_centric/test_privacy.py](../../tests/case_centric/test_privacy.py), [tests/case_centric/test_sacofa.py](../../tests/case_centric/test_sacofa.py)

### PM-ADV-020 · PRIPEL timestamp·속성 결과의 안전한 공개 경로

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 익명화한 제어흐름에 timestamp·속성을 privacy 정의 아래 결합하는가?
**다음 작업:** 지원 전제·탐색 한도·미판정 정의 → 지원/미지원 반례 → 종료·거부·부분 결과 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/pripel.py](../../src/pix/case_centric/pripel.py), [src/pix/case_centric/privacy.py](../../src/pix/case_centric/privacy.py) / 기존 테스트: [tests/case_centric/test_pripel.py](../../tests/case_centric/test_pripel.py), [tests/case_centric/test_privacy.py](../../tests/case_centric/test_privacy.py)


## R13 — 시각화

### OC-REL-003 · 객체 속성 이력·as-of 값의 시계열 화면

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체 속성 변화의 시간 순서와 이벤트 시점 값을 확인할 수 있는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/ocel/model.py](../../src/pix/ocel/model.py), [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### OC-VIEW-001 · OCPA OCPN 성능 view의 잔여 annotation

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCPN의 제어 흐름·성능 annotation·객체 구분을 읽기 쉬운 graph로 보여주는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/assets/viewer.js](../../src/pix/viewer/assets/viewer.js), [src/pix/viewer/export.py](../../src/pix/viewer/export.py), [src/pix/viewer/model_adapter.py](../../src/pix/viewer/model_adapter.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-001 · DFG performance·cost·timeline overlay

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** DFG의 빈도·성능·비용을 그림으로 설명하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/adapter.py](../../src/pix/viewer/adapter.py), [src/pix/viewer/assets/viewer.js](../../src/pix/viewer/assets/viewer.js), [src/pix/viewer/export.py](../../src/pix/viewer/export.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-002 · PN의 추가 performance·replay annotation

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Petri net의 구조·marking·replay/성능/alignment를 그림에 표현하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/assets/viewer.js](../../src/pix/viewer/assets/viewer.js), [src/pix/viewer/export.py](../../src/pix/viewer/export.py), [src/pix/viewer/model_adapter.py](../../src/pix/viewer/model_adapter.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-003 · OCDFG 성능 overlay·대형 graph 탐색

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCDFG에서 객체형별 경로·분모·성능을 확인하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/adapter.py](../../src/pix/viewer/adapter.py), [src/pix/viewer/assets/viewer.js](../../src/pix/viewer/assets/viewer.js), [src/pix/viewer/export.py](../../src/pix/viewer/export.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-004 · OCPN의 추가 성능·객체 참여 annotation

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** OCPN의 객체형·cardinality·marking과 성능을 확인하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/assets/viewer.js](../../src/pix/viewer/assets/viewer.js), [src/pix/viewer/export.py](../../src/pix/viewer/export.py), [src/pix/viewer/model_adapter.py](../../src/pix/viewer/model_adapter.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-005 · Process tree occurrence별 빈도 annotation

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Process tree operator와 빈도 annotation을 직접 확인하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-006 · 일반 BPMN 요소의 표현·저장 확장

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** BPMN의 gateway·flow·layout을 읽고 저장하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-007 · POWL BASIC/NET 표기의 부분순서 표현

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** POWL의 부분순서·operator·중첩 구조를 확인하는가?
**다음 작업:** 대안별 다른 결과가 나오는 최소 예제 → 정의·분모·순서 profile → 도메인 검토 → 구현·회귀.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-012 · Dotted chart의 속성 축·색·상대시간 옵션

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 시간축에서 이벤트 분포와 경로별 performance spectrum을 읽는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-013 · 분포 chart의 log 축·시간대·결측 표현

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Case 기간·이벤트 발생·속성 분포를 그래프로 확인하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-014 · 양측 DFG와 interleaving link의 통합 화면

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** 객체 연결·객체형 참여·interleaving을 그래프로 확인하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)

### PM-VIEW-015 · Variant duration의 정규화 배치·top-N

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도.
**업무 질문:** Decision tree와 variant별 duration을 설명하는가?
**다음 작업:** 제목의 잔여 옵션을 기존 기능과 차이 대조 → 공개 경로 확장 → 해당 R 묶음의 경계·실패·샘플 검증.
**착수 시 확인할 근거:** 기존 코드: [src/pix/viewer/visual_case_adapters.py](../../src/pix/viewer/visual_case_adapters.py), [src/pix/viewer/visual_chevrons.py](../../src/pix/viewer/visual_chevrons.py), [src/pix/viewer/visual_model_adapters.py](../../src/pix/viewer/visual_model_adapters.py) / 기존 테스트: [tests/viewer/test_visual_case_adapters.py](../../tests/viewer/test_visual_case_adapters.py), [tests/viewer/test_visual_chevrons.py](../../tests/viewer/test_visual_chevrons.py), [tests/viewer/test_visual_model_adapters.py](../../tests/viewer/test_visual_model_adapters.py)


## R14 — Agent·Schumpeter 경계

### PM-ADV-018 · 자연어 질의→embedding→case/event 검색

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 질문 문장과 가장 유사한 case·event를 embedding으로 선택하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/embedding_retrieval.py](../../src/pix/case_centric/embedding_retrieval.py), [src/pix/case_centric/embeddings.py](../../src/pix/case_centric/embeddings.py), [src/pix/case_centric/transformer_embeddings.py](../../src/pix/case_centric/transformer_embeddings.py) / 기존 테스트: [tests/case_centric/test_embedding_retrieval.py](../../tests/case_centric/test_embedding_retrieval.py), [tests/case_centric/test_embeddings.py](../../tests/case_centric/test_embeddings.py), [tests/case_centric/test_transformer_embeddings.py](../../tests/case_centric/test_transformer_embeddings.py)

### PM-EDGE-001 · LLM 서비스 호출 adapter

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 외부 LLM 서비스에 분석 질문을 전달하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-002 · 로그·모델·지표의 근거 보존 텍스트 요약

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 로그·모델·지표를 사람이 읽거나 LLM에 제공할 텍스트로 표현하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-003 · LLM 생성 regex 기반 trace 군집

**처리:** 설명 후 확인. 양측 불필요 표 유지. 정규식 군집 대신 패턴 가설 검사로 흡수하는 안은 별도 제안.
**업무 질문:** LLM이 제안한 패턴으로 trace를 군집화하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-004 · 자연어→검증 가능한 질의·필터

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 자연어를 로그 질의·필터 SQL로 바꾸어 적용하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-005 · 분석 가설·검사 질의 생성

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 데이터 가설과 검사 질의를 LLM으로 생성하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-006 · 그림만 보고 LLM으로 프로세스 설명

**처리:** 담당 변경. PIX 범위 제외. 그림 설명은 Schumpeter 후보로 보존하되 개발 확정은 아님.
**업무 질문:** 프로세스 그림을 LLM으로 설명하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-007 · Outlook 메일·캘린더 전용 수집기

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** Outlook 메일·캘린더를 event log 또는 OCEL로 수집하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-008 · OS 이벤트·Chrome/Firefox 이력 수집기

**처리:** 책임 확정. 후속 사용자 결정: 수집은 Agent, 계산은 PIX. 공통 입력 계약 우선, browser 전용 mapping은 필요 입증 시 추가.
**업무 질문:** Windows 이벤트와 Chrome·Firefox 방문 기록을 로그로 수집하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-009 · GitHub 이슈·활동 수집기

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** GitHub 이슈·활동을 로그로 수집하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-010 · Camunda·SAP O2C/회계 전용 connector

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** Camunda·SAP O2C·SAP 회계 데이터를 로그로 수집하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-EDGE-011 · 마우스·키 입력 전용 수집기

**처리:** 제외. 표기된 잔여 확장 제외. 기존 구현 유지. 실제 사용처가 생기면 재검토.
**업무 질문:** 마우스·키 입력을 live event로 수집하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-IO-019 · HTTP/HTTPS 로그 취득 adapter

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** HTTP/HTTPS 로그 주소를 입력하여 출처와 원본 파일을 확보한 뒤 읽는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [pyproject.toml](../../pyproject.toml), [src/pix/event_log/__init__.py](../../src/pix/event_log/__init__.py), [src/pix/io.py](../../src/pix/io.py)

### PM-STREAM-001 · Event/trace broadcaster·비동기 fan-out

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 도착하는 이벤트·trace를 등록한 계산기에 전달하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/revisable_stream.py](../../src/pix/case_centric/revisable_stream.py), [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py), [src/pix/object_centric/revisable_stream.py](../../src/pix/object_centric/revisable_stream.py) / 기존 테스트: [tests/case_centric/test_revisable_stream.py](../../tests/case_centric/test_revisable_stream.py), [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py), [tests/object_centric/test_revisable_stream.py](../../tests/object_centric/test_revisable_stream.py)

### PM-STREAM-003 · OCEL stream 분기·backpressure 연동

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** Dataframe·OCEL 이벤트를 분석별 stream으로 나누어 공급하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/stream_adapters.py](../../src/pix/case_centric/stream_adapters.py), [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py), [src/pix/object_centric/revisable_stream.py](../../src/pix/object_centric/revisable_stream.py) / 기존 테스트: [tests/case_centric/test_stream_adapters.py](../../tests/case_centric/test_stream_adapters.py), [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py), [tests/object_centric/test_revisable_stream.py](../../tests/object_centric/test_revisable_stream.py)

### PM-STREAM-010 · Checkpoint와 Hub의 durable offset·복구 계약

**처리:** 채택. 해당 잔여 범위의 설계·검증 대상. 수식·default·정확성 승인은 별도. PIX는 계산·입력/결과 계약만 담당. 취득은 Agent, 운영은 Schumpeter.
**업무 질문:** 온라인 계산 상태를 안전하게 저장하고 재시작하는가?
**다음 작업:** Agent/PIX/Schumpeter 책임과 메시지 정의 → PIX 경계 fixture 검증 → 외부 운영 검증 별도.
**착수 시 확인할 근거:** 기존 코드: [src/pix/case_centric/revisable_stream.py](../../src/pix/case_centric/revisable_stream.py), [src/pix/case_centric/streaming.py](../../src/pix/case_centric/streaming.py), [src/pix/object_centric/revisable_stream.py](../../src/pix/object_centric/revisable_stream.py) / 기존 테스트: [tests/case_centric/test_revisable_stream.py](../../tests/case_centric/test_revisable_stream.py), [tests/case_centric/test_streaming.py](../../tests/case_centric/test_streaming.py), [tests/object_centric/test_revisable_stream.py](../../tests/object_centric/test_revisable_stream.py)
