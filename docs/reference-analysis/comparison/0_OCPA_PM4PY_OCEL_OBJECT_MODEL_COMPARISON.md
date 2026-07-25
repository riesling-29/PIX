# OCPA와 PM4Py의 OCEL 객체 이해 방식 비교

**문서 유형:** Upstream 참조 비교 분석 / OCEL 객체 모델

**대상 프로젝트:** PIX

**비교 대상:** OCPA 1.3.3, PM4Py 2.7.23.3

**분석일:** 2026-07-24

**상태:** 기존 소스 분석 문서에 기반한 비교 기준선

---

## 0. 목적과 범위

이 문서는 OCPA와 PM4Py가 OCEL을 어떤 in-memory 객체로 이해하는지 비교한다.

비교 범위는 다음과 같다.

1. OCEL 객체의 중심 representation
2. Event, object 및 relation 표현
3. Graph와 process execution의 위치
4. Mutability와 consistency 경계
5. 파일 I/O 및 OCEL 2.0 의미론과의 관계
6. PIX canonical dataset과 derived computation에 대한 시사점

이 문서는 두 upstream source를 새로 실행하거나 round-trip test한 결과가 아니다. 다음 기존 분석 문서에서 확인된 내용을 교차 비교한다.

```text
../ocpa/0_OCPA_OVERALL_STRUCTURE_ANALYSIS.md
../ocpa/1_OCPA_OCEL_FILE_IO_ANALYSIS.md
../pm4py/0_PM4PY_OVERALL_STRUCTURE_ANALYSIS.md
../pm4py/1_PM4PY_OCEL_FILE_IO_ANALYSIS.md
```

성능, memory consumption, 모든 malformed input의 동작, 완전한 OCEL 표준 준수는 이 비교만으로 확정할 수 없다.

---

## 1. 비교 기준

### 1.1 OCPA 기준선

```text
Repository: ocpm/ocpa
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3
```

### 1.2 PM4Py 기준선

```text
Repository: process-intelligence-solutions/pm4py
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

### 1.3 직접 비교 시 주의점

OCPA 1.3.3의 package metadata는 `pm4py==2.2.32`에 직접 의존한다. 반면 PM4Py 분석 문서는 2.7.23.3을 대상으로 한다.

따라서 이 문서는 다음을 비교한다.

```text
OCPA 1.3.3 자체의 OCEL 모델
vs.
PM4Py 2.7.23.3 자체의 OCEL 모델
```

이 비교를 OCPA 내부에서 실제 호출되는 PM4Py 2.2.32와 PM4Py 2.7.23.3의 runtime 동작 비교로 해석해서는 안 된다.

---

## 2. 확인된 객체 구조

### 2.1 OCPA

OCPA의 최상위 `OCEL`은 여러 분석용 representation을 묶는 mutable composite다.

```text
OCPA OCEL
├── log: Table
├── obj: ObjectCentricEventLog
├── graph: EventGraph
├── parameters: dict
├── o2o_graph: ObjectGraph | None
└── change_table: ObjectChangeTable | None
```

각 representation은 동일한 논리적 log를 서로 다른 방식으로 나타낸다.

```text
Table
    Event 중심 DataFrame
    Object type별 column에 관련 object ID collection 저장

ObjectCentricEventLog
    Event와 Obj entity dictionary
    Event.omap으로 E2O 표현

EventGraph
    같은 object를 공유하는 timestamp-ordered event 사이의 edge

ObjectGraph
    O2O edge와 qualifier

ObjectChangeTable
    Object type별 attribute-change DataFrame
```

`process_executions`와 `variants`는 `OCEL` property에 처음 접근할 때 계산되고 instance 내부에 cache된다. Variant 계산은 `Table`에 `event_variant` column을 추가할 수 있다.

### 2.2 PM4Py

PM4Py의 `OCEL`은 역할별 Pandas DataFrame과 metadata를 묶는 mutable container다.

```text
PM4Py OCEL
├── events
├── objects
├── relations
├── o2o
├── e2e
├── object_changes
├── globals
└── parameters
```

각 table은 다음 의미를 가진다.

```text
events
    Event ID, activity, timestamp, event attribute

objects
    Object ID, object type, object attribute

relations
    E2O endpoint, qualifier 및 denormalized event/object metadata

o2o
    Source object, target object, qualifier

e2e
    Source event, target event, qualifier

object_changes
    Object, timestamp, changed field 및 변경 값
```

Graph와 process execution은 core `OCEL`의 필수 field가 아니다. 필요한 algorithm이나 projection이 DataFrame에서 파생한다.

---

## 3. OCEL을 이해하는 중심 관점

### 3.1 확인된 사실

OCPA는 하나의 log를 Table, entity dictionary, EventGraph로 동시에 materialize한다. Process execution과 variant 계산도 `OCEL` 객체가 lazy하게 제공한다.

PM4Py는 event, object 및 relation 종류를 DataFrame으로 분리한다. File importer와 exporter는 format별 외부 representation을 이 공통 container로 수렴시키거나 다시 serialize한다.

### 3.2 데이터 기반 해석

OCPA의 객체 구조는 다음 관점에 가깝다.

> OCEL은 object를 통해 연결된 event 흐름을 바로 분석할 수 있도록 여러 계산용 view를 결합한 작업공간이다.

PM4Py의 객체 구조는 다음 관점에 가깝다.

> OCEL은 event, object 및 relation record를 보관하고 여러 algorithm과 format adapter에 공급하는 관계형 dataset container다.

이 문장의 “작업공간”과 “관계형 dataset container”는 source class에 선언된 공식 용어가 아니라, 확인된 field 구성과 실행 경로를 설명하기 위한 해석이다.

OCPA가 하나의 authoritative representation과 나머지 derived cache 사이의 강제 경계를 도입하거나, PM4Py가 graph와 process execution을 core object invariant로 편입한 사실이 확인되면 이 해석을 철회해야 한다.

---

## 4. 같은 OCEL 요소에 대한 표현 차이

| OCEL 요소 | OCPA | PM4Py |
| --- | --- | --- |
| Event | `Table` row와 `Event` entity에 중복 표현 | `events` DataFrame row |
| Object | Object-type column reference와 `Obj` entity | `objects` DataFrame row |
| E2O | `Event.omap`, object-type별 event column, object-event mapping | 독립 `relations` DataFrame |
| E2O qualifier | OCEL 2.0 importer에서 EventGraph node attribute dictionary로 전달 | `relations`의 qualifier column |
| O2O | 선택적 `ObjectGraph` edge | 독립 `o2o` DataFrame |
| E2E | Core model에 확인된 field 없음 | 독립 `e2e` DataFrame |
| Object change | Object type별 `ObjectChangeTable` | 독립 `object_changes` DataFrame |
| Event ordering | 필수 `EventGraph`에 materialize | Timestamp 및 relation table에서 필요할 때 계산 |
| Process execution | `OCEL`의 lazy derived property | 별도 projection 또는 algorithm 결과 |
| Variant | `OCEL`의 lazy derived property와 Table mutation 가능 | 별도 algorithm/statistics 경로 |

### 4.1 E2O 차이

OCPA의 E2O는 여러 representation에 분산된다.

```text
Table:
    object type별 column

Entity view:
    Event.omap
    obj_event_mapping

EventGraph:
    object를 공유하는 event 사이의 ordering edge
```

PM4Py의 E2O는 `relations` DataFrame을 중심으로 표현된다.

```text
event ID
object ID
qualifier
event activity
event timestamp
object type
```

PM4Py의 relation은 endpoint와 qualifier를 명시하기 쉽지만 activity, timestamp, object type을 중복 저장하는 denormalization 때문에 `events` 또는 `objects` table과 불일치할 수 있다.

OCPA는 object-sharing event flow를 즉시 계산하기 쉽지만 동일 relation fact가 여러 representation에 존재하므로 drift 가능성이 있다.

### 4.2 Graph 차이

OCPA에서 `EventGraph`는 top-level `OCEL`의 필수 구성 요소다. Event ordering과 object-sharing semantics가 dataset object에 함께 들어간다.

PM4Py에서 graph는 core persistence model이 아니다. Graph, flattening, OC-DFG 등은 relation table에서 도출하는 computation에 가깝다.

이 차이는 다음 질문에 대한 답이 다르다는 뜻이다.

```text
"이 event들이 object를 통해 어떤 순서로 연결되는가?"

OCPA:
    OCEL 객체가 graph로 이미 보유해야 한다.

PM4Py:
    OCEL relation에서 필요할 때 계산할 수 있다.
```

---

## 5. Identity와 consistency 경계

### 5.1 OCPA

확인된 OCPA importer path에는 다음 동작이 있다.

- CSV에서 source event ID 대신 sequential ID 생성
- Classic JSON event dictionary key 대신 sequential integer ID 생성
- 일부 path에서 `Table`과 `EventGraph`는 source ID를 사용하지만 entity view는 1-based ID를 새로 생성
- Top-level constructor가 Table, entity dictionary 및 graph 사이의 일관성을 검증하지 않음
- Lazy calculation이 cache와 Table column을 변경

따라서 OCPA `OCEL` instance 하나가 생성되었다는 사실만으로 representation들이 동일한 event identity를 공유한다고 볼 수 없다.

### 5.2 PM4Py

확인된 PM4Py 경로에는 다음 동작이 있다.

- Identifier를 string으로 normalization
- Timestamp parsing과 temporal sort
- 필수 field가 null 또는 empty인 row 제거 가능
- 누락 qualifier 대체
- Relation filtering을 event, object, O2O, E2E 및 object change에 전파 가능
- Export 전에 consistency와 filtering을 실행하여 caller의 `OCEL`을 변경할 가능성

PM4Py는 OCPA와 같은 representation별 event-ID 재생성 문제가 비교 문서에서 확인되지는 않았다. 그러나 어떤 record가 변환 또는 제거됐는지 structured result로 반환하지 않으므로 evidence-preserving identity를 보장한다고 단정할 수 없다.

### 5.3 비교

| 위험 | OCPA | PM4Py |
| --- | --- | --- |
| 여러 representation 사이 identity drift | 높음: 확인된 ID-space 차이 존재 | 상대적으로 낮지만 table 간 중복 metadata 불일치 가능 |
| Invalid record 처리의 비가시성 | 공통 import result 없음 | Row 제거가 structured report 없이 발생 가능 |
| Query 또는 write의 mutation | Lazy property가 Table 변경 가능 | Export consistency/filtering이 object 변경 가능 |
| 생성 시 semantic validation | 없음 | 없음 |
| Source-to-normalized ID mapping | 없음 | 공통 contract 없음 |

“높음”은 정량적 발생 확률이 아니라 source에서 구체적인 ID-space 불일치 경로가 확인됐다는 상대 비교다. 실제 dataset에서 drift가 발생하는 빈도는 알 수 없음이다.

---

## 6. OCEL 2.0과 파일 I/O가 객체 이해에 미치는 영향

OCPA는 OCEL 2.0 SQLite/XML에서 읽은 O2O와 object change를 optional graph/table로 composite에 덧붙인다. 유일하게 확인된 exporter는 classic JSON이며 다음을 사용하지 않는다.

```text
ocel.log
ocel.graph
ocel.o2o_graph
ocel.change_table
```

따라서 OCPA의 객체 모델은 분석에 필요한 OCEL 2.0 구조를 부분적으로 보유할 수 있지만 persistence surface는 그 구조와 대칭적이지 않다.

PM4Py는 E2O, O2O, object change를 독립 table로 두고 다음 명시적 OCEL 2.0 format과 대응시킨다.

- Compact CSV
- Standard JSON
- XML
- SQLite
- CSV/Parquet bundle
- GZIP JSON/XML

PM4Py의 객체 모델은 format adapter의 공통 중간 representation 역할이 더 분명하다.

두 모델 모두 검사된 file-I/O layer에서는 E2E round trip을 지원하지 않는다. PM4Py에 `e2e` DataFrame이 존재한다는 사실만으로 file persistence가 지원된다고 해석해서는 안 된다.

---

## 7. 계산 구조에 미치는 영향

### 7.1 OCPA 방식

OCPA는 다음 계산에 유리하다.

- Object-sharing 기반 EventGraph traversal
- Connected-component process execution
- Leading-object process execution
- Graph hashing과 isomorphism 기반 variant
- OCPN discovery 및 object-centric conformance

그 대가는 canonical input과 derived state가 같은 mutable object에 섞인다는 점이다.

```text
input representation
+ derived graph
+ process-execution cache
+ variant cache
+ algorithm이 기록한 column
= 하나의 mutable OCEL
```

### 7.2 PM4Py 방식

PM4Py는 다음 경계에 유리하다.

- Format별 import/export
- Relation 종류별 filtering
- DataFrame 기반 통계와 projection
- Object type별 flattening
- Algorithm에 따라 필요한 graph 또는 model을 별도 생성

그 대가는 core `OCEL`만 보아서는 process execution이나 event graph semantics가 결정되지 않는다는 점이다. Projection operator, object type 선택 및 algorithm parameter가 별도로 필요하다.

---

## 8. PIX 관점의 설계 시사점

### 8.1 참조할 수 있는 요소

PM4Py에서 참조할 수 있는 요소는 다음과 같다.

- Event, object, E2O, O2O, E2E, object change의 명시적 분리
- Classic format과 OCEL 2.0 adapter의 분리
- Format adapter가 하나의 공통 dataset model로 수렴하는 구조
- Type별 relational 및 bundle layout

OCPA에서 참조할 수 있는 요소는 다음과 같다.

- Object-sharing EventGraph 의미론
- Connected-component와 leading-object projection
- Process execution과 object-centric variant 정의
- O2O graph와 object-change computation의 활용 방식

### 8.2 그대로 사용할 수 없는 요소

두 library 모두 다음 PIX 요구를 직접 충족하지 않는다.

- Immutable 또는 deterministic canonical dataset
- Source identifier와 normalized identifier mapping
- Rejected, inferred, coerced record의 구조화된 보고
- Omitted component와 lossy conversion의 명시
- Computation status와 operator identity
- Source evidence reference와 assumption
- Empty result, unavailable, unsupported 및 invalid-input의 구분

### 8.3 가능한 PIX 경계

다음은 비교 결과에서 도출한 설계 후보이며 승인된 architecture 결정이 아니다.

```text
ProcessDataset
├── events
├── objects
├── e2o_relations
├── o2o_relations
├── e2e_relations
└── object_changes
        │
        ├── EventGraph computation
        ├── ProcessExecution computation
        ├── Variant computation
        └── ObjectProjection computation
```

이 후보는 PM4Py처럼 relation record를 canonical dataset에서 명시적으로 분리하고, OCPA의 EventGraph와 process execution을 versioned derived computation으로 배치한다.

필요한 추가 계약은 다음과 같다.

```text
DatasetImportResult
├── dataset
├── identifier_mapping
├── normalized_fields
├── synthetic_fields
├── rejected_records
├── inferred_records
├── unavailable_components
├── assumptions
└── source_references

ComputationResult
├── operator
├── operator_version
├── status
├── source_dataset_identity
├── result
├── assumptions
└── evidence_references
```

PIX가 analysis-ready mutable workspace를 canonical dataset보다 우선하거나, source identity와 evidence lineage를 요구하지 않게 되면 이 설계 후보의 근거가 약해진다.

---

## 9. 미확인 사항

현재 문서 비교만으로는 다음을 확정할 수 없다.

- OCPA가 내부적으로 의도하는 authoritative OCEL representation
- 실제 dataset에서 OCPA representation drift가 발생하는 빈도
- PM4Py relation denormalization 불일치가 발생하는 빈도
- 두 객체 모델의 대규모 OCEL memory overhead
- Lazy graph/cache와 on-demand graph 계산의 상대 성능
- 모든 timestamp 및 primitive type의 round-trip equality
- Duplicate 또는 dangling relation에 대한 모든 variant의 runtime 동작
- PM4Py 2.2.32와 2.7.23.3의 OCEL model 차이가 OCPA integration에 미치는 영향
- 두 library가 OCEL 표준 전체를 완전히 준수하는지 여부

검증되지 않은 성능·발생 빈도·표준 준수 수치는 알 수 없음이다.

---

## 10. 유효기간과 철회 조건

이 비교는 다음 두 commit에 유효하다.

```text
OCPA:   de056e0203a3fa4a9bbc19a95e001eada323074a
PM4Py: 3329bbcbadce8764f7df660fd88636c30793fbd0
```

다음 경우 관련 판단을 재검토하거나 철회한다.

- OCPA가 하나의 canonical immutable OCEL model을 도입한 경우
- OCPA가 representation invariant와 source-ID mapping을 강제하는 경우
- OCPA가 graph와 cache를 canonical input에서 분리한 경우
- PM4Py가 relation denormalization을 제거하거나 immutable relation model을 도입한 경우
- PM4Py가 graph와 process execution을 core `OCEL` invariant로 편입한 경우
- 어느 쪽이든 structured import/export loss result를 도입한 경우
- 어느 쪽이든 E2E file serialization을 추가한 경우
- Runtime round-trip 및 mutation test가 기존 source 분석을 반증한 경우
- PIX의 canonical dataset 또는 evidence-lineage 요구가 변경된 경우

---

## 11. 최종 평가

**OCPA는 OCEL을 object를 통해 연결된 event 흐름을 즉시 분석하기 위한 `Table + entity dictionary + graph` 복합 작업공간으로 이해하고, PM4Py는 event·object·relation record를 format adapter와 algorithm에 공급하는 관계형 DataFrame dataset으로 이해한다. OCPA 방식은 process execution과 graph variant 계산에 직접적이지만 복수 representation의 identity와 consistency drift 위험이 크고, PM4Py 방식은 relation 및 OCEL 2.0 I/O mapping이 명시적이지만 destructive normalization, denormalized metadata 및 mutation을 공통 evidence report 없이 수행할 수 있다. PIX가 source identity와 evidence lineage를 우선한다면 PM4Py식 relation 분리를 canonical dataset의 출발점으로 삼고 OCPA식 EventGraph·process execution·variant를 명시적인 versioned derived computation으로 분리하는 설계가 현재 증거에 가장 부합한다.**
