# 잔여 구현 묶음: 공개 API 사용법

PIX는 Agent가 확보한 로컬 자료를 받는다. 이 문서의 API는 명시한 profile만 지원한다. [검증·한계 보고서](../reports/2026-09-18_PIX_RESIDUAL_CORE_IMPLEMENTATION.md)를 함께 참고한다.

## 로컬 CLI

설치 후 `pix`, 또는 `python -m pix`를 사용한다.

```console
python -m pix inspect input.xes
python -m pix dfg input.xes --output dfg-result.json
python -m pix ngrams input.xes --n-min 2 --n-max 3 --encoding count --output ngrams.json
python -m pix export-xes input.csv --case-column case --activity-column activity --timestamp-column time --output output.xes.gz
python -m pix dfg input.jsonocel --object-type order --tie-policy event_id
```

출력 경로가 이미 있으면 기본 거부하며 `--overwrite`로 명시한다. 종료 코드는 정상 0, 입력/실행 오류 2, partial 3, unavailable 4다. `dfg` 출력은 계산 결과 JSON이며 고전 DFG 파일 형식은 아래 별도 API를 사용한다. OCEL의 객체형은 사용자가 선택하고, 동시각 사건의 순서는 기본 거부한다. event_id 순서는 재현 가능한 선형화 정책이지 실제 선후관계가 아니다.

## XES와 객체 투영

```python
from pix.event_log import read_xes, read_xes_bytes, write_xes, xes_bytes

log = read_xes('input.xes')
receipt = write_xes(log, 'output.xes.gz')
restored = read_xes_bytes(xes_bytes(log))
```

```python
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec, project_object_cases,
)

projection = project_object_cases(ocel, ObjectCaseProjectionSpec('order'))
case_log = projection.case_log
```

투영 receipt의 원본 OCEL과 대응 정보를 함께 보관한다. 투영한 CaseLog만으로 모든 O2O 관계까지 재구성할 수 있다는 뜻은 아니다. 공유 event의 case별 occurrence ID는 서로 다르며 원본 event ID로 대응된다.

2026-09-20 보완의 `pix.object-case-projection.v2`는 기존 ComputationContext/build로 계산용 표현을 정규화한다. 같은 canonical OCEL과 spec은 같은 파생 CaseLog digest를 만든다. 원래 입력 순서·offset·import metadata는 `projection.source`에 유지한다. `describe()`는 별도 보관할 JSON-ready receipt이며 원본 OCEL 자체의 대체 저장 형식은 아니다. 이전 투영과 파생 digest가 달라지므로 캐시·파생 feature는 다시 계산한다. 일반 XES/CaseLog 순서·digest, OCEL Canonical V1과 계산 operator 전역 판본은 바뀌지 않는다.

## 입력 승인과 증거 보관

```python
from pix.ocel import import_ocel
receipt = import_ocel('input.jsonocel')
log = receipt.require_ocel(reject_timezone_assumptions=True)
```

시간대 없는 OCEL timestamp의 기본 UTC 가정은 유지한다. 경고·변환 횟수와 import receipt를 먼저 읽는다. 위 엄격 경로는 알려진 UTC 가정을 거부하며 import validity나 계산 status를 바꾸지 않는다. 가정이 없다는 사실이 수집 품질 전체의 인증은 아니다. XES는 timezone 없는 값을 보존하며 OCEL의 UTC 가정과 같은 동작이 아니다.

```console
python -m pix dfg input.jsonocel --object-type order --receipt-output evidence.json --output result.json --reject-timezone-assumptions
```

CLI result JSON은 기존 codec을 유지한다. `--receipt-output`을 지정하면 import 설명·mapping·admission·projection·결과 document를 별도 JSON으로 보관한다. 엄격 admission 거부도 receipt에 남는다. `inspect`는 입력 상태 조회이며 admission 승인이 아니다. receipt와 원본 snapshot을 결과와 함께 보관해야 한다. result만으로 input 경고를 복원할 수 없다. 두 출력은 개별 atomic publication이며 다중 파일 transaction은 아니므로 저장 오류 시 이미 생긴 파일을 확인한다.

## 공유 event와 학습 분리

```python
from pix.object_centric.case_projection import shared_event_case_groups, audit_projected_split
from pix.case_centric.feature_dataset import LeakageSplitSpec, leakage_safe_split

split = leakage_safe_split(projection.case_log, LeakageSplitSpec(
    shared_case_groups=shared_event_case_groups(projection)))
if split.value is not None:
    violations = audit_projected_split(projection, split.value.partitions,
                                      namespace='source-system/session')
```

그룹은 원본 event 공유를 기준으로 하며 재사용 자원 공유와 다르다. 분리 불가능하면 기존 split은 unavailable을 반환한다. namespace는 소비자가 소유하는 안정적인 ID 범위이고 content digest와 같은 개념이 아니다. 감사 API는 하나의 projection 안에서 모든 case가 지정된 split인지 확인한다. 복수 snapshot의 ID 조정과 일반적인 통계적 독립성 검증은 범위 밖이다. 투영의 전체 객체 이력은 online feature가 아니다. 관측 시점 feature에는 기존 `fit_observation_encoder`/`transform_observations`(시간 없는 trace/log 속성 제외) 또는 명시 `as_of`의 객체 feature를 사용한다.

## 지표와 미확정의 해석

`cycle_seconds`는 완전한 service 관측 case의 service interval 합집합 길이를 그 case 수로 나눈 값이다. 두 case가 동일한 10초 동안 처리되면 이 값은 5초이며 평균 service 10초와 다르다. 기존 수식·codec은 유지한다. bucket의 distinct 객체 수를 더해 전역 distinct 수로 사용하지 않는다.

경로는 `occurrence_count = duration.count + excluded_count`를 보존한다. complete→complete 간격은 자동으로 대기시간이 아니다. 비근무시간 0과 달력 범위 미정의, 결측·빈 case·미완료 탐색을 구별한다. n-gram의 evidence cap은 근거 반환만 줄이고 집계는 유지하지만 계산 자원 한도는 unavailable이다. 계산 status뿐 아니라 issues·coverage·payload의 None/종료 사유를 함께 읽는다.

## 로컬 소비자 예제

```console
python examples/review_consumer.py --output <새 디렉터리>
```

artifact@v1 테스트 성공을 artifact@v2의 검증으로 사용하지 않는 예제다. 원본 JSON OCEL, import/projection receipt, 계산 결과, version별 증거 선택을 함께 저장한다. v2의 테스트 부재는 False가 아닌 None이며 열린 관측이다. 예제의 선택 if문은 소비자 정책이지 신규 PIX 승인 알고리즘이 아니다. computation ID는 재현 요청 identity이며 진실성 보증 서명이 아니다. 배포·재시도·Hub 운영은 소비자 책임이다.

## n-gram: 학습과 적용 분리

```python
from pix.case_centric.context_ngrams import (
    ContextNGramSpec, fit_context_ngrams, transform_context_ngrams,
)

fit = fit_context_ngrams(
    log, ContextNGramSpec(ngram_min=1, ngram_max=3, encoding='tfidf'),
)
if fit.value is not None:
    result = transform_context_ngrams(log, fit.value)
```

별도 검증 로그에도 같은 `fit.value`를 적용한다. 각 단계의 status와 issues를 확인한다. token_attributes에 속성 이름을 지정하면 활동과 typed 속성 값을 합친 token이 된다. 결측은 기본 거부이며 `missing='tag'`를 명시할 수 있다. 증거 개수 제한은 원본 occurrence 집계와 별개다. 자원 한도에 도달한 결과를 완전한 행렬로 취급하지 않는다.

## 경로 성능과 업무 달력

```python
from pix.case_centric.path_performance import (
    PathPerformanceSpec, measure_path_performance,
)

result = measure_path_performance(
    log, PathPerformanceSpec(grouping='variant_position'),
)
```

기본 시간은 이웃한 두 event의 timestamp 차이다. `target_timestamp_key`로 target start 속성을 지정하거나 `calendar`에 `BusinessCalendar`를 전달할 수 있다. 달력은 유한 UTC 구간이며 `weekly_business_calendar`로 근무 요일·휴일·시간대 조건에서 생성할 수 있다. 범위 밖은 제외 진단으로 반환한다.

## 교환 형식

```python
from pix.ocel.export import export_bundle, export_ocel1_json
from pix.model_io import read_dfg, write_dfg, project_dfg_exchange

bundle = export_bundle(ocel, 'log.zip', storage='parquet')
legacy = export_ocel1_json(ocel, 'legacy.jsonocel')
```

Parquet는 선택 의존성 PyArrow가 필요하다. CSV bundle의 빈 문자열 속성은 기존 reader의 결측 해석과 충돌하므로 거부한다. OCEL 1은 정보 손실이 있으면 기본 거부하며 `allow_loss=True`를 명시한 경우 receipt.losses를 확인한다. DFG 파일은 빈도 그래프만 담으므로 `project_dfg_exchange`의 생략 정보를 보존한다.
