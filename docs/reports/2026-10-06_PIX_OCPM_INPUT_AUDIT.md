# NEXT-01 공개 입력 의미 감사 — 1차

기준 제품 코드: `a0688f34e557c885c145051485072fd0623f263f`. 작업 브랜치: `docs/ocpm-input-audit-20261006`.
범위: 공개 표면 목록과 아래 20개 함수의 정의·기존 반례 연결. 제품 코드·계산 수식·runtime enum·registry 등급·177개 사용자 선택은 변경하지 않는다.

## 조사 모집단과 재현

[CSV](ocpm-input-audit-2026-10-06/public-input-inventory.csv)는 `pix.api`, `pix.object_centric`와 그 lazy `_MODULES`, `pix.case_centric.context_ngrams`를 대상으로 한다. `__all__`을 우선하며 없는 모듈은 그 모듈에서 정의한 공개 함수·클래스를 사용한다. alias는 실제 정의별로 합치고 export 경로는 모두 보존한다. 공개 클래스에 직접 정의된 공개 메서드도 포함한다. 상속·dunder·private 메서드, 다른 case-centric 모듈, viewer, CLI는 이 분모 밖이다. **PIX 전체 API 수나 알고리즘 수가 아니다.**

이 범위에서 170개 정의(함수 136, 메서드 34)를 찾았다. 20개 함수는 아래 표에서 정의를 확인했으며 나머지 150개는 `not_reviewed`로 남겼다. CSV의 `definition_checked_not_replacement_verified`는 함수 전체의 정확성·참조 대체 승인·실제 도메인 수락이 아니다. 자동 추출은 함수명·위치·인자·반환 annotation만 채우며 qualifier/history 사용 의미를 추정하지 않는다.

```bash
python tools/export_ocpm_input_inventory.py \
  --output docs/reports/ocpm-input-audit-2026-10-06/public-input-inventory.csv \
  --reviews docs/reports/ocpm-input-audit-2026-10-06/review-map.json
```

실제 개발 interpreter로 실행한다. 첫 실행은 `action_planning`에 `__all__`이 없어 실패했다. 위의 명시적 fallback을 추가한 뒤 성공했으며 재생성 bytes도 비교했다. 이름이 일치하지 않는 review-map은 오류로 거부한다. source line은 이 기준 코드의 탐색 편의일 뿐 안정 identity가 아니다.

## 입력 의미 사용표

함수의 전체 경로와 선언 위치는 CSV에서 행 ID로 연결한다. '보존'은 계산 사용과 다르다. '없음'은 이 profile에 observation cutoff 인자가 없다는 뜻이며 데이터가 자동으로 cutoff-safe라는 뜻이 아니다. OCEL 계산의 `ComputationContext`는 builder로 시각을 UTC 정규화한다. 원본 관계·속성은 계산에 직접 쓰지 않아도 canonical source identity에 포함될 수 있다.

| 행 / 공개 함수 | spec·선택·관계 | 속성 이력·cutoff·순서 | 결과·모집단 및 경계 |
| --- | --- | --- | --- |
| IN-01 `discover_ocdfg` | `OCDFGSpec`; E2O qualifier·객체형 선택; O2O는 edge 생성에 미사용 | 이력 값은 count에 미사용; cutoff 없음; timestamp/tie policy | `event_pair_count`, `unique_object_count`, `occurrence_count`; 복수 qualifier로 같은 객체 발생 중복 금지 |
| IN-02 `measure_object_context` | `ObjectContextSpec`; selected E2O 객체 universe·모델 binding-prefix; model digest | 객체 속성 이력 미사용; cutoff 없음; tie 정책; 종료 `excluded` | micro behavior set count와 full-scope fitness/precision ratio; 0분모·탐색 미완료는 `None` |
| IN-03 `replay_object_log` | `ObjectReplaySpec`; E2O qualifier 선택·중복 제거·구체 객체 binding; model digest | 이력 feature 미사용; cutoff 없음; lexical DAG·동률 정책 | inserted/missing/remaining token과 search/limit; silent state와 binding budget 분리 |
| IN-04 `replay_flattened_object_log` | 같은 spec; 객체별 projected unit-arc net; 공동 cardinality·synchronization 손실 | 이력 미사용; cutoff 없음; 객체별 timestamp/event ID | token count 합산 fitness; shared event가 여러 객체 행에 등장; unweighted 평균 아님 |
| IN-05 `discover_etot` | `ETOTSpec.qualifiers`; E2O activity–object-type incidence; O2O 미사용 | 이력 미사용; cutoff 없음; 시간 선후행 연산 아님 | `qualified_relations` / `event_object_pairs` / `events` / `objects` 중 고유 집합 수. OCDFG occurrence 정의와 다름 |
| IN-06 `discover_otg` | `OTGSpec`; E2O에서 관계 종류별 ObjectGraph 구성; 방향 profile | 이력 미사용; cutoff 없음; 관계 종류별 tie 정책 | `(source type, relation kind, target type)`별 객체 edge 수; 이벤트 빈도와 다름 |
| IN-07 `compare_object_graphs` | 같은 타입·동일 spec의 ObjectGraph/ETOTGraph/OTGGraph 2개; graph pair identity | 원본 OCEL 이력 재조회 없음; 입력 graph profile 상속 | edge 집합 coverage/support/Jaccard와 min-frequency overlap; node/실행 행동/align fitness 미보장; 0분모 미정 |
| IN-08 `object_attributes_as_of` | `AttributeAsOfSpec`; object IDs·attribute names; E2O/O2O qualifier 선택 없음 | `at` 이전 최신 assignment, inclusive/exclusive; 미래 대입 금지 | 값·실제 assignment time·선언 여부, 결측 `None`; O2O에 lifetime 추정 안 함 |
| IN-09 `query_object_relations` | `ObjectRelationSpec`; O2O qualifier·inbound/outbound/both·선택 ID | 속성 이력 미사용; cutoff 없음; untimed O2O | 원래 source/target/qualifier records; 조회 방향이 원본 edge를 뒤집지 않음 |
| IN-10 `filter_ocel` | `OCELFilterSpec`; ID/type/activity·object-event policy; 명시적 O2O closure; qualifier 필터 인자 없음 | event window `[start,end]`; `window_with_prior`/`preserve_all` | 이전 마지막 assignment와 구간 내 이력 보존 또는 전체 보존; closure는 다른 객체형을 추가할 수 있음 |
| IN-11 `evaluate_filter_predicates` | `OCFilterPredicateSpec`; attribute/lifecycle/performance; qualifier는 mode별 모집단 | object attribute는 명시 as-of; lifecycle 고유 first/last·rework; performance는 nested spec | selected/unknown ID와 decisions; unknown include/exclude/error; 동률 endpoint는 임의 확정 안 함 |
| IN-12 `filter_ocel_by_predicate` | `OCPredicateFilterSpec`; IN-11 + 명시 projection policy | predicate의 as-of 의미와 projection history 보존을 구별 | materializable sublog·decisions·parent computation ID; unknown과 population을 보존 |
| IN-13 `extract_object_features` | `ObjectFeatureSpec`; execution 객체형·E2O qualifier; feature별 사용 정보가 다름 | `as_of`, prefix strict_before/through_timestamp; event/object attribute 사용은 요청 feature별 | input/target role·rows·graphs·unknown; full-log execution cohort는 retrospective이며 streaming assignment 보장 아님 |
| IN-14 `ocpn_to_causal_net` | `ObjectConversionSpec`; 모델만 입력; place당 producer/consumer 제약 | OCEL qualifier·이력·cutoff 해당 없음 | `exact`, `transition_mapping`, `loss_report`, `refusal_reasons`, `profile`; choice를 지우는 입력은 모델 생성 없이 거부 |
| IN-15 `causal_net_to_ocpn` | 같은 spec; marker alternatives·shared-object 제약·copy budget | OCEL qualifier·이력·cutoff 해당 없음 | 대안 binding은 transition 복제로 표현; 독립/disjoint selection·budget 초과는 거부; ID 대응·제거 사유 보존 |
| IN-16 `measure_performance` | `OCPerformanceSpec`; E2O qualifier·type/activity·profile·event start attribute | 객체 이력 미사용; cutoff 없음; timestamp/tie 정책; observed lifecycle와 생성/종료 시각 구별 | 정수 µs/count, population/known/unknown, exact mean numerator/denominator; OPERA 요청은 token witness 경로 필요 |
| IN-17 `measure_replay_performance` | `OCReplayPerformanceSpec`; replay의 선택·source/model 대응; FIFO token 생산 순서 | event start attribute 사용; 객체 이력 미사용; cutoff 없음; silent max-input clock | 실제 소비 token의 arrival evidence; unknown initial/repaired inputs를 0으로 만들지 않음 |
| IN-18 `enhance_ocpn` | `EnhancedOCPNSpec`의 replay+timing; model/source/attachment 검사 | IN-03/17 의미 상속; 전체 이력 feature 사용 주장 없음 | 모델·replay·performance·transition diagnostics; samples/known/unknown/mean을 annotation에 연결 |
| IN-19 `mark_lifecycle_qualifiers` | `LifecycleQualifierSpec`; source E2O qualifier 선택; 출력 역할·collision policy | 객체 이력이 아닌 참여 event first/last; cutoff 없음; tie 3정책 | singleton은 first+last; 기존 역할 덮어쓰기 금지; observed endpoint이지 생성/종료 증명 아님 |
| IN-20 `project_object_cases` | `ObjectCaseProjectionSpec`; 객체형 선택; qualifier 필터 없음, 원본 qualifier 보존 | full history 보존; cutoff feature 아님; reject/event_id tie | profile v2, occurrence→source·excluded/tied IDs·source/derived digest; O2O는 source receipt에만 보존 |

## 반례·검증 근거 연결

아래는 독립 기대값·경계가 들어 있는 기존 파일을 읽어 연결한 것이다. 파일 전체를 독립 oracle이라고 부르지 않는다. 같은 제품 코드의 Python 3.12 전체 테스트는 앞선 2026-10-06 실행에서 10,524 pass/40 skip/1,169 subtests였으며 이번 감사의 새 실행으로 세지 않는다. Python 3.10 실행 결과는 NEXT-04의 별도 기록에 속한다.

| 행 | 기존 테스트 파일 | 확인할 수락 반례 |
| --- | --- | --- |
| 01 | `tests/compute/test_ocdfg.py` | shared/repeated pair 3 count 구별, 복수 qualifier 불변 |
| 02 | `tests/compute/test_object_context.py`, `test_object_context_oracle.py` | prefix behavior 집합 손계산·예산·0분모 |
| 03–04 | `tests/object_centric/test_conformance.py` | shared binding·고립 객체·silent 한도·joint/flattened별 기대값 |
| 05–09 | `tests/object_centric/test_relations.py` | ETOT 네 모집단, OTG 방향, boundary/no-future, edge 손계산·0분모·profile mismatch |
| 10 | `tests/object_centric/test_filtering.py` | window prior assignment, O2O closure·고립·empty 선택 |
| 11–12 | `tests/object_centric/test_filter_predicates.py`, `test_advanced_filtering.py` | as-of inclusive/exclusive, unknown/complement 분리, 동률 endpoint, predicate→sublog |
| 13 | `tests/object_centric/test_features.py` | append-future prefix 불변, future join, retrospective target, unknown/학습 분리 |
| 14–15 | `tests/object_centric/test_models.py` | joint binding/marking 보존, causal alternatives ID 대응, 표현 불가 제약 |
| 16–18 | `tests/object_centric/test_performance.py`, `test_model_integration.py` | observed lifecycle vs gap, repeated token·unknown input, event/model attachment 일치 |
| 19 | `tests/object_centric/test_enrichment.py` | singleton 양쪽 role, 기존 qualifier collision, 선택 역할·동률 |
| 20 | `tests/object_centric/test_case_projection.py`, `tests/test_review_boundaries.py` | 원본 대응·동률·shared-event split·full-history 경계 |

## P1 판정과 다음 작업

| 요구 | 1차 판정 | 다음 확인 / 판단 철회 조건 |
| --- | --- | --- |
| P1-01 context | 문서·정책 노출 필요 | binding-prefix/termination/모집단을 소비자 예제로 노출. 독립 oracle 반례 시 해당 계산 재검토 |
| P1-02 OPERA | 문서·정책 노출 필요 | token timing·요약·transition annotation 존재. 요구한 arc별 annotation 전체 보장은 별도 대조; 모든 OPERA 요구 완료로 올리지 않음 |
| P1-03 replay | 문서·정책 노출 필요 | silent 한도 구현 확인; flooding의 참조별 정의·동등성은 추가 조사. 새 enum 먼저 만들지 않음 |
| P1-05 filter | 기존 충족(검토한 profile 범위) | 시간·lifecycle·performance 경로 존재. 실제 도메인 조건이 current modes로 표현 안 되면 별도 공백 |
| P1-06 ETOT/OTG | 기존 충족(edge 집합·빈도 비교 범위) | `compare_object_graphs`가 이미 지원. node/실행 conformance까지 요구하면 별도 정의 필요 |
| P1-07 conversion | 기존 충족(제한된 exact/refusal 계약) | 양방향·loss/refusal 존재. 모든 모델 변환 가능이나 upstream 동치로 확대하지 않음 |
| P1-08 enrichment | 기존 충족(관측 endpoint profile) | first/last/singleton/collision 구현 존재. 실제 lifecycle 생성·종료 요구와 구별 |
| P1-09 표준 판본 | 검증 차단(판본별 상세 대조 미완료) | 이전 계획의 pre5 발견은 구현 변경 지시 아님; 고정 PDF·schema field diff 필요 |

NEXT-01 전체 완료는 아니다. 다음은 150개 미검토 행 중 constraints·advanced filter·learning/stream의 입력 의미와 cutoff부터 채우고, P1-02의 arc annotation·P1-03의 flooding·P1-09 판본 diff를 분리해서 닫는다. 필요 정의와 반례가 확보되기 전 새 알고리즘을 시작하지 않는다. 기존 177 선택과 ILP 보류를 유지한다.

이번 읽기 범위에서는 새 계산 결함을 입증하지 않았다. 반례가 없다는 것이 결함 부재 증명은 아니다. 위 SHA·profile에 한해 유효하며 구현·spec·관측 모집단 변경이나 독립 반례 시 관련 행을 수정한다. 전체 대체율·실무 효용·미측정 성능은 알 수 없음이다.
