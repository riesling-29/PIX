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
