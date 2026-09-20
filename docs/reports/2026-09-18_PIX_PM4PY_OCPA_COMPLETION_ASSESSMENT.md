# PIX의 PM4Py·OCPA 대비 기능 구현 현황 평가

평가일: **2026-09-18**. 분석 대상 코드: **`65cf9d557cfcbe1f8159b9a8600bb1aa60fe3fc9`**.
대상 브랜치는 `feat/ocel-readers-v0.2.0`이며, 이번 문서는 계산 코드를 변경하지 않고 구현·검증 기록을 평가한다.

이 보고서는 ‘몇 % 만들어졌는가’를 **명시 profile 구현 비율**, **부분 지원까지 포함한 대응 범위**,
**참조 대체 검증 승인 비율**로 나누어 산정한다. 서로 다른 지표를 하나의 완성률로 합치지 않는다.
아래 수치는 고정한 비교 항목을 센 값이다. 남은 개발 공수·모든 옵션의 구현 비율·실무 성공률은 **알 수 없음**이다.

## 1. 비교 대상과 분모

공식 PyPI를 다시 확인한 비교 판본은 PM4Py **2.7.23.8**, OCPA **1.3.4**다.
기존 SCOPE-01에 고정했던 판본 및 wheel SHA-256과 일치한다.
이번 확인은 배포 판본 확인이며 두 패키지를 설치해 전 알고리즘을 실행 대조한 것은 아니다.
[PM4Py 공식 배포](https://pypi.org/project/pm4py/), [OCPA 공식 배포](https://pypi.org/project/ocpa/).

| 비교 모집단 | PM4Py | OCPA | 합계 | 포함 범위 |
|---|---:|---:|---:|---|
| 전체 SCOPE-01 | 264 | 70 | **334** | 계산, 모델, 입출력, 시각화, 외부 연결·보조 기능 |
| 계산 및 필수 계산 지원 | 208 | 60 | **268** | 기존 native mining union의 계산 행 |
| 계산 분모 밖의 제품 표면 | 56 | 10 | **66** | 입출력·시각화·외부 adapter 등. 전체 평가에서는 제외하지 않음 |

**분모의 단위는 ‘원본 소스 검토 행’이며 서로 다른 알고리즘 수가 아니다.**
한 행이 여러 variant를 묶기도 하고, PM4Py와 OCPA의 비슷한 기능이 각각 한 행을 차지하기도 한다.
따라서 334는 중복 제거된 수학적 알고리즘 합집합 크기가 아니다. 합산 비율은 두 비교 목록의 검토 행 비율이다.
기존의 구현 패키지 83개나 W4 packet 25개를 분모에 더하지 않는다.

같은 이유로 작은 parser와 복잡한 alignment가 각각 한 행을 차지한다. 이 비율을 투입 공수나 남은 일정으로
환산할 수 없다. Native API/자료형으로 기능을 제공하면 대응으로 인정할 수 있으며, upstream Python 객체를
그대로 받는 drop-in 호환성이나 동일한 화면 배치까지 자동 요구하지 않는다. 그 차이는 따로 남긴다.

## 2. 분류 규칙과 증거 강도

| 표기 | 이 보고서의 의미 | 이 상태만으로 주장하지 않는 것 |
|---|---|---|
| **A: 명시 profile 구현** | 업무 질문에 대응하는 native 입력·계산·출력 또는 표현 경로와 검증 근거가 연결됨. 정해진 profile 범위를 지원한다고 분류 | 참조 행의 모든 variant/옵션 지원, 실무 규모 품질, 참조 대체 승인 |
| **B: 부분 지원** | 관련 경로는 있지만 행이 묶은 기능 일부, 중요한 변환/표현/운영 범위 또는 실행 근거가 남음 | 남은 부분이 정확히 50%라는 주장 |
| **E: 외부 runtime 미검증** | 어댑터/계약은 있지만 실제 외부 runtime 실행을 확인하지 못함 | 구현 경로가 있다는 이유만으로 학습·추론 완료 처리 |
| **N: 대응 경로 미확인** | 공개 코드 표면과 기록에서 해당 기능의 대응 경로를 확인하지 못함 | 유사한 생성자·JSON 출력·다른 reader가 기능을 대신한다는 추정 |

산식은 다음 두 개만 사용한다.

- **명시 profile 구현 비율 = A / 전체 행 수 × 100**
- **부분 지원 포함 대응 비율 = (A + B) / 전체 행 수 × 100**

B에 임의로 0.5점을 주는 가중 평균은 사용하지 않았다. 두 비율 사이를 ‘실제 완성률의 신뢰구간’으로
해석해서도 안 된다. A에도 참조 옵션 차이가 남을 수 있고, B의 내부 구현량은 일정하지 않다.

행별 A/B 판정은 **코드·문서에 근거한 평가자의 분류 판단**이다. 그 판정을 전제로 한 개수·백분율 계산은
재현 가능한 사실 집계다. 사용자의 도메인 승인과 구별한다. 기존 계산 268행을 전부 새로 독립 검산한 것이
아니라, 이전 registry 분류를 유지하고 최신 변경으로 해소된 gap을 재평가했다.

증거는 [SCOPE-01](../requirements/scope-01/replacement_registry.json),
[계산 union](../requirements/union-2026-09-15/implementation_registry.json),
[모델·W4 추가 registry](../requirements/models-w4-2026-09-17/implementation_registry.json),
[시각화 대체표](../requirements/2026-09-15_PIX_VISUALIZATION_UNION.md), 현재 소스와
[최종 통합 검증 보고서](2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md)를 연결했다.
기존 registry의 판정이나 hash를 이 보고서에 맞춰 덮어쓰지 않았다.

## 3. 라이브러리별 전체 기능 비교

입출력·시각화·외부 연결을 포함한 **전체 334행 기준**이다.

| 비교 대상 | 전체 | A | B | E | N | 명시 profile 구현 | 부분 지원 포함 대응 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **PM4Py** | 264 | 110 | 132 | 1 | 21 | **41.7%** | **91.7%** |
| **OCPA** | 70 | 47 | 22 | 0 | 1 | **67.1%** | **98.6%** |
| 전체 비교 행 | 334 | 157 | 154 | 1 | 22 | **47.0%** | **93.1%** |

PM4Py 41.7%는 ‘PM4Py 코드의 41.7%를 복제했다’는 뜻이 아니다. 고정 비교표 264행 중
110행을 명시 profile 구현으로 분류했다는 뜻이다. 부분 지원 132행에도 상당한 계산 코드가 있다.
반대로 91.7%는 호출 가능한 관련 경로의 범위를 나타내며 ‘나머지 8.3%만 만들면 끝’이라는 뜻이 아니다.

OCPA의 98.6%도 완성 판정이 아니다. 해당 목록 70행 중 69행에서 명시 profile 또는 부분 대응을 확인했다는 뜻이다.
일부 차이는 옵션 확장으로 해결되지만, OC discovery·conformance·variant의 동치 정의 차이는 별도 판단이 필요하다.
단순한 함수 추가와 같은 작업량으로 볼 수 없다.

## 4. 계산 엔진만 분리한 비교

사용자가 PIX의 중심으로 지정한 native 계산 엔진은 **268행**으로 따로 본다.

| 참조 라이브러리의 계산 행 | 전체 | A | B | E | 명시 profile 구현 | 부분 지원 포함 대응 |
|---|---:|---:|---:|---:|---:|---:|
| PM4Py | 208 | 95 | 112 | 1 | **45.7%** | **99.5%** |
| OCPA | 60 | 42 | 18 | 0 | **70.0%** | **100.0%** |
| 합계 | 268 | 137 | 130 | 1 | **51.1%** | **99.6%** |

이 계산 목록에는 대응 경로가 전혀 없는 N 행이 없지만, B 130행과 E 1행이 남아 있다.
계산 전 영역에 코드가 분포해 있다는 사실과, 세부 variant까지 대체할 수 있다는 판단은 다르다.

### Case-centric과 Object-centric

| 계산 도메인 | 전체 | A | B | E | 명시 profile 구현 | 부분 지원 포함 대응 |
|---|---:|---:|---:|---:|---:|---:|
| **Case-centric** | 168 | 67 | 100 | 1 | **39.9%** | **99.4%** |
| **Object-centric** | 100 | 70 | 30 | 0 | **70.0%** | **100.0%** |

Object-centric 100행에는 **PM4Py의 OC 계산 40행과 OCPA의 60행**이 함께 들어간다.
‘PM4Py=Case-centric, OCPA=Object-centric’으로 단순 치환하지 않았다.
두 도메인의 비율은 해당 계산 모집단에만 적용하며, 혼합 입출력·외부 연결 66행에 억지로 case notion을 부여하지 않았다.

## 5. 분야별로 남은 폭

아래는 SCOPE-01의 원래 영역 구분을 유지한 전체 334행 집계다.
`performance`는 원본 OCPA 전용 행이고, PM4Py의 여러 성능 계산은 `data` 등에 있다.
`ocel`도 파일 reader만의 구분이 아니므로 영역 이름을 새 기능 분모로 오해하지 않아야 한다.

| 영역 | 전체 | A | B | E/N | A 비율 | 남은 범위의 예 |
|---|---:|---:|---:|---:|---:|---|
| 발견 | 29 | 14 | 15 | 0/0 | 48.3% | 발견 variant·fallthrough·noise/default별 대응 |
| 적합성 | 30 | 18 | 12 | 0/0 | 60.0% | 탐색/비용/종료 규칙, 분해 alignment 및 근사 profile 차이 |
| 모델 | 36 | 14 | 20 | 0/2 | 38.9% | 일반 BPMN·확장 net 분석·GeneticMatrix·변환 및 분해 범위 |
| 데이터·통계·필터 | 59 | 32 | 26 | 0/1 | 54.2% | 참조의 옵션·분모·시간·결측·변환 세부 정의 |
| OCEL 분석 | 39 | 27 | 12 | 0/0 | 69.2% | OC projection/qualifier/실행·동치 정의 차이 |
| 조직·자원 분석 | 11 | 0 | 11 | 0/0 | 0.0% | SNA·roles 등의 native 계산은 있지만 참조 family의 지표/기본값 범위가 부분 |
| OC 성능 | 6 | 4 | 2 | 0/0 | 66.7% | Replay·구간·분모·동시성 가정 |
| 규칙·제약 | 10 | 9 | 1 | 0/0 | 90.0% | 미지원 predicate/발견 profile와 전체 참조 대응 |
| 고급 분석 | 29 | 12 | 16 | 1/0 | 41.4% | 완전한 feature inventory, clustering·decision·drift·embedding 실행 범위 |
| 시뮬레이션 | 10 | 3 | 7 | 0/0 | 30.0% | Concurrent PN/resource 통합, stochastic map·종료 정책·참조 sampler |
| 스트리밍 | 10 | 0 | 9 | 0/1 | 0.0% | 공개 iterator, async fan-out, backpressure, durable/backend 대응 |
| Action | 6 | 4 | 2 | 0/0 | 66.7% | 구조·관측 성능 impact의 세부 대응. 인과효과는 별도 문제 |
| 입출력 | 25 | 12 | 7 | 0/6 | 48.0% | XES/OCEL legacy/bundle export, DFG 파일, URL adapter |
| 시각화 | 21 | 8 | 13 | 0/0 | 38.1% | Cost/performance overlay, 일반 BPMN, log 축·normalized duration 배치 |
| 외부 연결·CLI | 13 | 0 | 1 | 0/12 | 0.0% | LLM·업무 시스템·사용자 행동 수집·CLI |

**0.0%인 조직 분석과 스트리밍에도 실제 구현이 있다.** 이 표의 A 기준으로 승격된 행이 없다는 뜻이며
코드가 전혀 없다는 뜻이 아니다. 시각화 38.1% 역시 Graphviz·무채색 스타일의 미감 점수가 아니다.
고정한 시각화 행에서 모든 요구 표현이 연결되지 않은 B 행이 많다는 의미다.
기존 시각화 대체표의 26개 family는 원래 SCOPE 시각화 21행에 대응시켜 한 번씩만 집계했다.

## 6. 최신 W4가 바꾼 것

9월 15일 계산 registry의 분류는 A에 해당하는 `native_profile` **126행**, partial **141행**, E **1행**이었다.
이번 평가에서는 최신 코드가 특정 결손을 해소한 **11행**을 B에서 A로 재분류했다.
그 결과 계산 profile 비율은 **126/268=47.0% → 137/268=51.1%**, 약 **4.1%p** 증가한다.
이는 이번 W4 개발량이 전체 공수의 4.1%라는 뜻이 아니다.

| 재분류한 행 | 과거 결손 | 현재 확인한 추가 경로 | 유지하는 경계 |
|---|---|---|---|
| PM-MODEL-003 | 독립 stochastic net 저장 계약 부재 | StochasticPetriNet·파라미터 출처·저장/발화 | 범용 GSPN/CTMC 분석 아님 |
| PM-MODEL-005 | Transition-bordered 변환 부재 | Tree→transition-bordered PN 및 언어 검산 | 지원 tree 연산자·한도 |
| PM-MODEL-021 | 형식별 활동명 읽기/변경 부재 | 5개 모델군의 occurrence 보존 relabel | 모든 모델·NetworkX 호환 아님 |
| PM-ADV-002 | Cutoff·검열 계약 부재 | 관측시점 prefix dataset | 다중 landmark/as-of 속성 join 별도 |
| PM-ADV-011 | 다음 활동의 완료/검열 구분 부족 | 관측·검열 target | 예측 classifier 자체 아님 |
| PM-ADV-012 | 외부 완료 근거·우측 검열 부재 | Next/remaining-time target | upstream timestamp/default 동등성 미검증 |
| OC-MODEL-002 | 객체형별 local source-target subnet 부재 | Typed subprocess·경계 손실 근거 | Directed-walk profile, soundness 인증 아님 |
| OC-MODEL-003 | Subprocess·hiding·reduction 조합 부재 | 명시 pipeline | 투영 전후 전체 동기화 보존 아님 |
| OC-FEAT-007 | K-step sample/target 부재 | Timestamp-block k-step dataset | 시간·execution identity가 있는 행 |
| OC-FEAT-009 | Inverse/fit/predict/MAE 부재 | Native 선형회귀·역변환·held-out 평가 | 임의 estimator API·비선형 모델 아님 |
| OC-ACT-004 | 제공된 marking만 분석 | 검증 replay prefix의 운영 모집단 추론 | 실제 상태 관측·벽시계 cutoff 아님 |

11개 재분류의 근거는 [행별 평가](completion-2026-09-18/ROW_ASSESSMENT.md)와
[W4 구현 보고서](2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md)에 연결했다.
이 승격을 보류하면 계산 A 비율은 다시 **47.0%**다. 따라서 이 판단 차이가 지표에 미치는 영향도 확인할 수 있다.
기존 126행 자체의 분류를 재심사하면 그 비율도 바뀔 수 있다. 이것은 통계적 신뢰구간이 아니다.

W4 25개 packet은 중복을 제거하면 원본 **59행**에 연결된다. 그중 `added_or_extended` packet의
대상은 **42행**이다. 42행이 전부 새로 완료됐다는 뜻은 아니다. 기존 구현 재연결과 같은 행에 대한 여러 개선을
분리했다. PNML·PTML 2행은 별도로 전체 제품 A에 추가했고, 일반 BPMN 교환 행은 B로 유지했다.

새 알고리즘이 생겼어도 다음 행들은 B로 남겼다.

- **PM-MODEL-019:** 최대 분해/재결합은 추가됐지만 참조 merge utility 범위와 weighted 입력 경계까지 모두 종료하지 않았다.
- **PM-MODEL-015:** Coverability는 추가됐지만 일반 WOFLAN·liveness·모든 soundness 진단을 대신하지 않는다.
- **PM-MODEL-011:** Trie 변환은 추가됐지만 GeneticMatrix 변환이 남았다.
- **PM-ADV-001·005:** 누출 방지 분할과 sequence tensor는 추가됐지만 참조의 분할·전체 event feature schema가 모두 대응된 것은 아니다.
- **PM-SIM-009:** 다중 자원·달력·fitting이 추가됐지만 일반 PN semaphore simulation과 같은 계산은 아니다.
- **PM-STREAM-010:** 정정/checkpoint는 추가됐지만 Redis·thread-safe backend·분산 durability까지 구현한 것은 아니다.

## 7. 아직 경로를 확인하지 못한 22행

이 목록은 부분 구현 B 154행과 별도로, 현 공개 표면에서 대응 경로를 확인하지 못한 N 항목이다.
‘작은 기능이므로 제외’하거나 ‘Schumpeter로 옮길 수 있으므로 완료’로 처리하지 않았다.

| 묶음 | ID | 개수 | 필요한 기능 |
|---|---|---:|---|
| Case/OC log 출력 | PM-IO-002, PM-IO-013, PM-IO-014, OC-IO-005 | 4 | XES writer, OCEL 1/enriched/CSV/classic SQLite, compact/bundle export |
| 모델·source I/O | PM-IO-017, PM-IO-019 | 2 | DFG 파일 교환, HTTP/HTTPS 취득 adapter |
| 파일 stream | PM-STREAM-002 | 1 | 공개 XES/CSV event·trace iterator와 종료/오류/backpressure 계약 |
| LLM 연결·텍스트 추론 | PM-EDGE-001~006 | 6 | 질의, 텍스트 추상화, regex 군집, 자연어 SQL, 가설 생성, 그림 설명 |
| 외부 source 수집 | PM-EDGE-007~011 | 5 | Outlook, OS/browser, GitHub, Camunda/SAP, 마우스·키 입력 |
| 명령행 | PM-EDGE-012 | 1 | 공개 CLI 명령·결과·오류 계약 |
| 편의 parser | PM-UTIL-008~010 | 3 | 활동 문자열 로그, tree·POWL 텍스트 문법 |

XES reader 내부의 XML chunk iterator는 공개 event-stream API가 아니다.
CaseLog 생성자도 활동 문자열 parser와 같지 않고, native 결과 JSON은 XES/DFG 교환 형식을 대신하지 않는다.
반면 사용자의 제품 방향에서 외부 LLM·수집기의 책임을 Schumpeter로 옮기기로 결정하면 분모를 별도로 재설계할 수 있다.
현재는 그러한 범위 변경을 자동 적용하지 않았다.

외부 runtime 미검증 E 1행은 **PM-ADV-009 Transformer embedding**이다.
Native 선형회귀가 추가됐다는 이유로 Transformer 실행 근거까지 확보된 것으로 바꾸지 않았다.

## 8. 검증 결과가 말해주는 것과 말해주지 않는 것

대상 commit의 최종 기록은 **Python 10,413 passed, 53 skipped, 1,169 subtests passed**,
Node **249 passed**, 별도 실제 Chromium **26 passed**다. Wheel에서는 runtime 파일 235개의 일치와
32개 계산 결과의 저장/복원, 모델 교환 및 시각화를 확인했다.
이 수치는 [기존 통합 보고서](2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md#11-통합-검증과-재현)의
해당 실행 기록을 인용했으며 이번 문서 작성 중 전체 suite를 다시 실행한 수치가 아니다.

현재 registry에서 참조 대체 검증이 승인된 행은 **0/334**, 계산 행으로 좁혀도 **0/268**이다.
따라서 **등록된 대체 검증 승인 비율은 0%**다. 이것을 ‘PIX 계산의 정확도가 0%’ 또는 ‘아무것도 완성하지 못했다’로
해석하면 안 된다. 많은 독립 기대값·반례 검사가 있지만, 행별 참조 variant 전체에 대한 완료 판정은 아직 없다.

반대로 테스트 10,413개가 통과했다는 이유로 기능 100%라고 할 수도 없다. 여러 테스트가 하나의 profile을 검증하며,
아직 없는 variant의 테스트는 통과 목록에 나타나지 않는다. 특히 최신 기본 suite의 Parquet 관련 14개 skip은
환경 실행 근거의 공백이다. CSV/Parquet bundle을 묶은 PM-IO-011은 이번 평가에서 B로 분류했다.
API 부재와 환경 미검증을 같은 이유로 기록하지 않았다.

PM4Py/OCPA의 오류나 우연한 기본값을 그대로 재현해야만 ‘대체’인 것은 아니다.
W5의 종료 기준은 **해당 업무를 PIX의 명시된 의미로 수행할 수 있는지**, **독립 검산이 맞는지**,
**참조와 다른 부분 및 호환 손실이 설명되는지**로 잡을 수 있다. 다른 의미를 채택한다면 행별로
`참조 의미 지원`과 `승인된 PIX 대안`을 구분해야 한다. 기존의 모든 false를 일괄 true로 바꾸는 방식은 근거가 부족하다.

## 9. 다음 개발을 고르는 기준

이 순서는 구현 시간 예측이나 사용자 승인된 범위 변경이 아니라, 이번 격차에 근거한 제안이다.

| 순서 | 권장 묶음 | 먼저 확인할 종료 조건 |
|---|---|---|
| 1 | 행별 의미·variant 인수 기준 고정 | 빈 입력·동률·결측·비용·종료·한도와 지원 profile를 ID별로 선언. 독립 기대값 및 반례 연결 |
| 2 | 실제 교환을 막는 writer | XES 및 우선 사용할 OCEL export에 원본 순서·중첩 속성·qualifier/이력의 보존 또는 명시 거절 검증 |
| 3 | Case-centric의 넓은 B 범위 정리 | 필요한 발견·alignment·모델 변환·조직 지표를 선택해 reference variant/PIX 대안을 하나씩 닫기 |
| 4 | OC 핵심 경로의 대체 판정 | 실제 Agent OCEL에서 execution→variant→conformance→performance→action의 동일 객체·event·분모 근거 검토 |
| 5 | W4 운영 경계 검증 | 지연·정정·재시작·한도·검열·동시성 및 실제 corpus의 성능/메모리 측정 |
| 6 | 외부 연결의 제품 책임 결정 | PIX adapter와 Schumpeter 책임을 명시. 제외한다면 전체 대체율과 계산 엔진 비율을 별도 유지 |

Object-centric profile 비율이 더 높다는 사실은 PIX+Schumpeter 경로를 먼저 검토할 이유가 될 수 있다.
다만 현재 숫자만으로 실운영 안정성이나 ‘처음 하는 작업도 실패 없음’을 추론할 수는 없다.
그 확률과 전체 잔여 공수는 **알 수 없음**이다.

## 10. 재현 파일과 판단을 철회할 조건

- [334행 전체 평가표](completion-2026-09-18/ROW_ASSESSMENT.md): 질문·판정·이유·소스/테스트 링크.
- [계산 가능한 평가 데이터](completion-2026-09-18/assessment.json): 집계, baseline 상태, 최신 W4 근거, 과거 gap의 별도 보존, 소스 fingerprint.
- [재집계 도구](../../tools/report_replacement_progress.py): 분모·중복·경로·교차표 검사를 포함한다. 알고리즘을 실행하거나 대체 승인을 내리는 도구가 아니다.

저장소 루트에서 `python tools/report_replacement_progress.py`로 JSON과 행별 표를 다시 생성할 수 있다.
이 도구의 재분류 목록은 평가 판단을 공개하기 위한 것으로, 함수 이름을 검색해 자동으로 완성을 선언하지 않는다.
판본·scope·분류 정책을 바꿔 실행했다면 이 본문의 날짜·숫자·해석도 함께 갱신해야 한다.

이번 보고서 작성 검증에서는 334개 ID의 중복 없음, 268/66 분모의 배타적 분할, 라이브러리별 합계와
백분율, W4 연결 59행/신규·확장 대상 42행을 별도 계산으로 대조했다.
본문·행별 표의 로컬 링크 **574개**를 확인했고 누락은 없었다. 재집계 도구 Ruff와 기존 W4 registry의
strict hash/self-test도 통과했다. 이 검사는 보고서 집계의 검증이며 알고리즘의 새로운 실행 검증은 아니다.

이번 수치는 명시한 commit, 고정 참조 판본, 334/268행 분모와 A/B 규칙에서만 유효하다.
다음이 확인되면 관련 행을 재분류하고 모든 비율을 다시 계산한다.

1. A 행의 공개 경로가 실행되지 않거나 입력·분모·반례에서 선언한 결과를 만족하지 못한다.
2. 하나의 핵심 누락을 단순 옵션 차이로 잘못 분류했거나, N 행에 이미 대응 구현이 존재한다.
3. SCOPE에 중복·누락이 발견되거나 참조 판본·PIX 계약·제품 책임 범위가 바뀐다.
4. 실제 corpus에서 의미 보존·정정·종료·저장 결과의 오류가 재현된다. 테스트 개수로 해당 반례를 무시하지 않는다.

## 11. 최종 판단

**명시 profile 구현 기준으로 PIX는 전체 비교 행의 47.0%, 계산 엔진 행의 51.1%를 지원한다고 분류할 수 있다.**
라이브러리별 전체 비율은 **PM4Py 41.7%, OCPA 67.1%**, 계산만 보면 **PM4Py 45.7%, OCPA 70.0%**다.
부분 지원을 포함한 대응 범위는 각각 훨씬 넓지만, 이를 완성률로 부르지 않는다.
현재 상태는 계산 전반의 구현 기반을 갖추고 세부 의미·variant·교환·운영 경계를 닫아야 하는 단계다.
**전체 대체의 정확한 완성률은 아직 알 수 없으며, 등록된 참조 대체 검증 승인은 0%**다.
