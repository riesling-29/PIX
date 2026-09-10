<!-- 한국어 버전 -->

# OCPA OCEL 데이터 모델 및 파일 입력·출력 분석

**문서 유형:** Upstream 참조 분석 / OCEL 데이터 모델 및 파일 I/O 기준선

**대상 프로젝트:** PIX

**참조 라이브러리:** OCPA

**참조 저장소:** `https://github.com/ocpm/ocpa.git`

**분석 브랜치:** `main`

**분석 커밋:** `de056e0203a3fa4a9bbc19a95e001eada323074a`

**OCPA 버전:** `1.3.3`

**분석일:** 2026-07-23

**상태:** 소스 수준 OCEL 데이터 모델 및 입력·출력 분석 기준선

---

## 0. 목적과 범위

이 문서는 OCPA가 OCEL 객체를 어떻게 구성하고, CSV·classic JSON/XML·OCEL 2.0 SQLite/XML을 해당 representation으로 어떻게 읽으며, 어떤 형식으로 내보내는지를 설명한다.

분석 범위는 다음과 같다.

1. 최상위 `OCEL` composite dataclass
2. Table, entity dictionary, EventGraph representation
3. O2O graph와 object-change table
4. Lazy process-execution 및 variant cache
5. Format별 importer와 exporter dispatch
6. Event/object ID, attribute, E2O, qualifier, O2O, object change, E2E 보존
7. Import/export 중 normalization과 mutation
8. PIX contract와 adapter에 대한 예비 시사점

이 문서는 source-level 분석이다. 모든 sample에 대한 runtime round-trip equality, 처리량, memory 사용량 또는 완전한 OCEL 표준 준수를 입증하지 않는다.

---

## 1. 분석 기준

```text
Repository: ocpm/ocpa
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3
```

주요 검사 영역은 다음과 같다.

```text
ocpa/objects/log/ocel.py
ocpa/objects/log/variants/
ocpa/objects/log/converter/
ocpa/objects/log/importer/csv/
ocpa/objects/log/importer/ocel/
ocpa/objects/log/importer/ocel2/
ocpa/objects/log/exporter/ocel/
sample_logs/
tests/
```

현재 로컬 Python 환경에는 pytest가 없어 runtime test를 실행하지 못했다. 따라서 실행하지 않고 source에서 도출한 동작은 문서에서 source-level 관찰로 분류한다.

---

## 2. 전체 객체·I/O 아키텍처

OCPA는 외부 log 하나를 여러 in-memory representation으로 변환한다.

```text
외부 OCEL/CSV file
    ↓
format factory 또는 parser
    ↓
Pandas event table
    ├──→ Table
    ├──→ ObjectCentricEventLog
    └──→ EventGraph
            ↓
        OCPA OCEL
        ├── log
        ├── obj
        ├── graph
        ├── parameters
        ├── o2o_graph       # optional
        └── change_table    # optional
```

Classic JSON exporter는 전체 composite를 serialize하지 않는다. `ocel.obj`의 metadata와 raw event/object dictionary만 읽어 JSON-OCEL 1.0 형태로 쓴다.

```text
OCPA OCEL
    ↓
ocel.obj.meta + ocel.obj.raw
    ↓
classic JSON-OCEL 1.0
```

따라서 importer와 exporter가 다루는 내부 representation 범위가 서로 다르다.

---

## 3. OCEL 데이터 모델

### 3.1 최상위 `OCEL`

`ocpa.objects.log.ocel.OCEL`은 다음 mutable dataclass다.

```python
@dataclass
class OCEL:
    log: Table
    obj: ObjectCentricEventLog
    graph: EventGraph
    parameters: dict
    o2o_graph: ObjectGraph = None
    change_table: ObjectChangeTable = None
```

각 필드의 책임은 다음과 같다.

| Field | Type | 의미 |
| --- | --- | --- |
| `log` | `Table` | Event 중심 Pandas DataFrame과 lookup cache |
| `obj` | `ObjectCentricEventLog` | Event·object entity dictionary와 metadata |
| `graph` | `EventGraph` | Event ordering/object-sharing 기반 directed graph |
| `parameters` | `dict` | Process execution, variant 및 import 설정 |
| `o2o_graph` | `ObjectGraph \| None` | OCEL 2.0 O2O directed graph |
| `change_table` | `ObjectChangeTable \| None` | Object type별 attribute-change DataFrame |

`OCEL` constructor는 세 필수 representation이 서로 같은 event/object/relation을 나타내는지 검증하지 않는다.

### 3.2 `Table`

`Table`은 전달된 event DataFrame을 복사하고 `event_id`를 index로 설정한다.

```text
Table
├── _log                 # copied Pandas DataFrame
├── _object_types        # parameters["obj_names"]
├── _object_attributes
├── _numpy_log
├── _column_mapping
└── _mapping             # event ID → column value lookup
```

내부 event table의 관례적 column은 다음과 같다.

```text
event_id
event_activity
event_timestamp
event_start_timestamp
event_<attribute>
<object-type-1>          # 관련 object ID list/set
<object-type-2>
...
```

OCPA의 E2O relation은 독립 relation table보다 object-type별 event column으로 표현된다.

### 3.3 Entity representation

`ObjectCentricEventLog`는 metadata와 raw data를 묶는다.

```text
ObjectCentricEventLog
├── meta: MetaObjectCentricData
└── raw: RawObjectCentricData
    ├── events: dict[event_id, Event]
    ├── objects: dict[object_id, Obj]
    └── obj_event_mapping: dict[object_id, event_id list]
```

Entity shape은 다음과 같다.

```python
Event(
    id,
    act,
    time,
    omap,
    vmap,
)

Obj(
    id,
    type,
    ovmap,
)
```

`ObjectCentricEventLog.__post_init__()`은 activity set, activity별 event, object-type별 object, event별 object, object별 timestamp-ordered sequence와 activity trace를 즉시 materialize한다.

### 3.4 EventGraph

`EventGraph`는 `nx.DiGraph` wrapper다.

```python
@dataclass
class EventGraph:
    eog: nx.DiGraph
```

`eog_from_log()`은 object type별로 같은 object를 공유하는 event를 timestamp-ordered table 순서에 따라 연결한다. 각 object에 대해 이전 event에서 다음 event로 edge를 추가한다.

Qualifier dictionary가 제공되면 NetworkX node attribute로 설정한다. 별도의 typed E2O relation object나 qualifier table은 없다.

### 3.5 ObjectGraph와 ObjectChangeTable

OCEL 2.0 importer는 선택적으로 다음 representation을 추가한다.

```python
@dataclass
class ObjectGraph:
    graph: nx.DiGraph


@dataclass
class ObjectChangeTable:
    tables: dict[str, pd.DataFrame]
```

O2O qualifier는 graph edge attribute로 저장된다. Object change는 object type별 DataFrame에 `object_id`, timestamp, changed-field indicator와 value column을 보관한다.

### 3.6 Lazy process execution과 variant

다음 property는 최초 접근 시 계산된다.

```text
process_executions
process_execution_objects
process_execution_mappings
variants
variant_frequencies
variant_graphs
variants_dict
```

기본 process execution 방식은 connected component이고 기본 variant 방식은 two-phase다.

Variant 계산은 임시 `event_objects` column을 추가했다가 제거하며, 최종 `event_variant` column을 `Table.log`에 기록한다. 따라서 read-like property 접근이 내부 DataFrame을 변경할 수 있다.

### 3.7 Mutability와 정합성 경계

OCPA `OCEL`은 immutable dataset contract가 아니다.

- Top-level dataclass field를 교체할 수 있다.
- Table의 public DataFrame을 변경할 수 있다.
- Event, Obj, graph, change table도 mutable이다.
- Lazy calculation이 cache와 log column을 변경한다.
- `Table.remove_object_references()`는 in-place helper다.
- Source comment는 해당 helper가 모든 representation의 consistency를 보장하지 않는다고 명시한다.

따라서 `OCEL`이 생성되었다는 사실만으로 Table, entity dictionary, EventGraph, O2O graph, change table이 서로 일치한다고 볼 수 없다.

---

## 4. 공개 입력 API

OCPA에는 PM4Py처럼 extension 하나로 모든 OCEL format을 자동 routing하는 단일 `read_ocel2()` facade가 없다. Format family별 module을 직접 import한다.

| 입력 | 호출 surface | 반환 |
| --- | --- | --- |
| CSV | `objects.log.importer.csv.factory.apply` | 기본 `OCEL` |
| Classic JSON-OCEL | `objects.log.importer.ocel.factory.apply` | `OCEL` |
| Classic XML-OCEL | 같은 factory의 `variant="ocel_xml"` | `return_df=True`일 때 DataFrame 또는 tuple |
| OCEL 2.0 SQLite | `objects.log.importer.ocel2.sqlite.factory.apply` | `OCEL` |
| OCEL 2.0 XML | `objects.log.importer.ocel2.xml.factory.apply` | `OCEL` |

확인된 importer에는 OCEL 2.0 standard JSON, GZIP JSON/XML 또는 Parquet bundle 경로가 없다.

---

## 5. 공통 Import 처리

Format별 세부 구현은 다르지만 대체로 다음 representation을 만든다.

```text
external records
→ event DataFrame
→ object type별 related-object column
→ Table
→ Event/Obj dictionary
→ ObjectCentricEventLog
→ EventGraph
→ optional ObjectGraph/ObjectChangeTable
→ OCEL
```

공통 structured import result는 없다. Importer는 다음을 별도 field로 보고하지 않는다.

- normalized field
- regenerated identifier
- rejected record
- inferred record
- unsupported component
- lossy conversion
- assumption
- source record reference

---

## 6. CSV Import

### 6.1 입력 형태

CSV event table은 parameter로 column 의미를 지정한다.

```python
parameters = {
    "obj_names": ["application", "offer"],
    "val_names": [],
    "act_name": "event_activity",
    "time_name": "event_timestamp",
    "sep": ",",
}
```

Object type column의 cell은 object ID list 또는 set 형태의 string으로 parsing한다.

### 6.2 Variant

CSV factory는 다음 variant를 제공한다.

```text
to_df
to_obj
to_ocel       # default
```

`to_ocel`은 `to_df`, `Table`, `df_to_ocel`, `eog_from_log`를 조합한다.

### 6.3 Identifier와 timestamp

`to_df`는 input에 event ID가 있더라도 source code상 row 위치를 기반으로 다음 ID를 새로 만든다.

```python
event_id = [str(i) for i in range(len(df))]
```

이 DataFrame으로 `ObjectCentricEventLog`를 만들 때 `df_to_ocel`은 다시 1부터 event를 enumerate한다. 따라서 동일한 CSV import 결과 안에서도 `Table`·`EventGraph`의 0-based ID와 entity representation의 1-based ID가 다를 수 있다.

Timestamp는 Pandas datetime으로 변환하고 event table을 timestamp 기준으로 sort한다. Start timestamp parameter가 없으면 completion timestamp를 `event_start_timestamp`로 복제한다.

### 6.4 보존 한계

CSV importer는 다음을 표현한다.

- event activity와 timestamp
- event attribute
- object type별 E2O reference
- 선택적 별도 object attribute table

다음은 지원 경로가 확인되지 않았다.

- E2O qualifier
- O2O relation
- object change history
- E2E relation

CSV exporter는 존재하지 않는다.

---

## 7. Classic JSON-OCEL Import

### 7.1 외부 representation

Classic JSON importer는 다음 key를 사용한다.

```text
ocel:global-log
ocel:events
ocel:objects
ocel:activity
ocel:timestamp
ocel:omap
ocel:vmap
ocel:type
ocel:ovmap
```

### 7.2 Parsing

```text
JSON dictionary
→ parse_events
→ parse_objects
→ MetaObjectCentricData
→ RawObjectCentricData
→ ObjectCentricEventLog
→ jsonocel_to_csv
→ Table + EventGraph
→ OCEL
```

### 7.3 Event ID 재부여

`parse_events()`는 JSON의 event dictionary key를 내부 ID로 보존하지 않고 iteration 순서에 따라 `0, 1, 2, ...`를 부여한다.

```text
external event key → internal sequential integer ID
```

`Event.id` type annotation은 string이지만 이 경로에서는 integer가 들어간다. Python dataclass가 runtime type을 강제하지 않기 때문에 허용된다.

### 7.4 Timestamp와 synthetic attribute

Timestamp가 `Z`로 끝나면 `Z`를 제거한 뒤 `datetime.fromisoformat()`을 호출한다. 이 경우 명시적인 UTC timezone 정보가 없는 naive datetime이 될 수 있다.

`vmap`에 `start_timestamp`가 없으면 event timestamp를 사용해 synthetic `start_timestamp`를 추가한다. 이후 classic JSON export는 이 보강된 value를 그대로 `vmap`에 쓸 수 있다.

### 7.5 Object attribute와 representation 차이

Raw `Obj.ovmap`에는 JSON object attribute가 유지된다. 그러나 JSON-to-CSV converter가 반환하는 object DataFrame은 현재 empty이며 importer는 이를 `None`으로 재설정한다. 결과적으로 entity representation에는 attribute가 있어도 `Table`의 object-attribute lookup representation에는 없을 수 있다.

또한 public classic JSON factory는 `file_path_object_attribute_table` argument를 받지만 selected importer를 호출할 때 해당 값을 전달하지 않고 `None`을 고정해 넘긴다. 따라서 factory surface를 통한 별도 object-attribute table 입력은 실제로 적용되지 않는다.

### 7.6 알려진 source comment

Source comment는 global metadata에 선언되었지만 어떤 event에서도 참조되지 않는 object type이 DataFrame column으로 나타나지 않아 downstream alignment error가 전파될 수 있다고 명시한다.

또한 Table parameter의 `val_names`를 구성하는 expression에 대해 source TODO가 “incorrectly concatenated”라고 직접 표시한다. 따라서 classic JSON event attribute가 entity view와 Table view에서 같은 이름으로 노출된다고 가정해서는 안 된다.

---

## 8. Classic XML-OCEL Import

Classic XML variant는 이름과 type annotation상 `OCEL` importer처럼 보이지만 실제 source는 다음과 같이 동작한다.

```text
return_df=True
→ event DataFrame
→ object DataFrame 또는 event DataFrame만 반환

return_df=False
→ ValueError(
    "Returning ocel from xml is not supported yet. Use return_df=True."
  )
```

따라서 classic XML에서 OCPA composite `OCEL`로 직접 수렴하는 경로는 현재 지원되지 않는다.

추가 특성은 다음과 같다.

- Event와 object attribute를 XML tag type에 따라 parsing한다.
- `omap`을 object type별 event column으로 변환한다.
- `event_id`를 float, 이후 int로 변환하므로 numeric-castable ID를 가정한다.
- Classic XML exporter는 없다.

---

## 9. OCEL 2.0 SQLite Import

### 9.1 읽는 table

Importer는 다음 OCEL 2.0 relational table을 사용한다.

```text
event
object
event_map_type
object_map_type
event_<event-type>
object_<object-type>
event_object
object_object
```

### 9.2 Event reconstruction

`event` table을 기본으로 type-specific event table을 merge한다. Type별 timestamp column을 하나의 `event_timestamp`로 합치고 event attribute column에 `event_` prefix를 붙인다.

`Table`과 `EventGraph`는 SQLite의 source event ID를 사용한다. 그러나 함께 생성되는 `ObjectCentricEventLog`는 `df_to_ocel`을 거치며 event를 1부터 다시 enumerate한다. 따라서 하나의 composite 안에서 source-ID graph/table과 regenerated-ID entity view가 공존할 수 있다.

### 9.3 E2O와 qualifier

`event_object`와 `object`를 join해 event별 object type column을 구성한다.

Qualifier는 다음 dictionary로 읽는다.

```text
event_id
└── object_id → qualifier
```

이 dictionary는 `eog_from_log()`에 전달되어 EventGraph node attribute로 설정된다. Dedicated E2O relation table은 최종 `OCEL`에 남지 않는다.

### 9.4 O2O

`object_object`는 `nx.DiGraph`로 변환한다.

```text
source object → target object
edge attribute: qualifier
```

### 9.5 Object change

`object_map_type`으로 type-specific object table을 찾고, object type별 DataFrame dictionary를 `ObjectChangeTable`에 저장한다.

### 9.6 Source-level 위험

Factory와 implementation은 mutable default argument인 `parameters={}`를 사용하며, importer는 필요하면 해당 dictionary에 `obj_names`를 추가한다. 여러 호출 사이의 default parameter state 공유 가능성은 runtime test가 필요한 source-level 위험이다.

`event_object`를 object type별로 aggregate한 frame의 index는 source event ID다. 반면 update 대상 `event_df`는 source event ID를 index로 설정하지 않은 기본 RangeIndex 상태다.

```text
aggregated_data index:
    e1, e2, ...

event_df index:
    0, 1, ...

event_df.update(aggregated_data[object_type])
```

따라서 string event ID에서는 Pandas index alignment 때문에 object reference가 event table에 반영되지 않을 수 있다. Compatible current dependency로 수행한 제한된 probe에서는 24개 relational constraint를 만족한 sample의 object reference가 비어 entity object가 0건이 되었고, 뒤이은 debug sample helper에서 `ValueError`가 발생했다.

OCPA의 pinned Pandas 1.3.5 환경을 현재 Python에서 재현하지 못했으므로 runtime exception 자체는 보조 근거다. 그러나 source index가 명시적으로 정렬되거나 pinned dependency probe가 반증하기 전까지 string event ID의 E2O 보존은 보장된 것으로 판단하지 않는다.

SQLite exporter는 없다.

---

## 10. OCEL 2.0 XML Import

### 10.1 Parsing 대상

Importer는 다음 section을 처리한다.

```text
object-types
event-types
objects
events
```

### 10.2 Object와 O2O

Object ID와 type을 mapping하고 object relationship을 `ObjectGraph` edge로 만든다. Qualifier는 edge attribute로 저장한다.

### 10.3 Object attribute change

Object attribute는 object type별 change row로 수집한다.

```text
object_id
attribute value column
chngfield
event_timestamp
```

`time="0"`은 string `"0"`으로 유지되고, 그 외 값은 datetime으로 parsing된다. 동일 timestamp column 안에 string과 datetime이 섞일 수 있다.

### 10.4 Event와 E2O qualifier

Event는 `event_id`, `event_activity`, `event_timestamp`, object type별 related-object list로 구성한다. E2O qualifier는 SQLite와 마찬가지로 event별 dictionary를 거쳐 EventGraph node attribute로 전달된다.

`Table`과 `EventGraph`는 XML source event ID를 사용하지만 `ObjectCentricEventLog`는 DataFrame converter에서 1-based ID를 새로 만든다. SQLite와 같은 representation별 ID-space 차이가 생길 수 있다.

### 10.5 Event attribute 처리 위험

Parser는 XML event attribute 이름에 먼저 `event_` prefix를 붙인 뒤, unprefixed name으로 구성된 event-type declaration dictionary를 조회한다.

```text
declaration key:
    pr_creator

lookup key:
    event_pr_creator
```

표준적인 attribute name에서는 lookup이 실패해 `except` branch가 실행되므로 lexical value 자체는 `event_<name>` column에 기록된다. 그러나 declared primitive type은 적용되지 않고 string fallback으로 parsing된다.

반대로 declaration name 자체가 이미 `event_` prefix를 포함해 lookup이 성공하는 비표준적 경우에는 `try` branch에 value assignment가 없어 attribute가 누락될 수 있다.

따라서 일반적인 OCEL 2.0 XML에 대한 확인된 위험은 “선언된 event attribute 전체 누락”보다 “값은 남지만 declared type을 잃고 string으로 수렴”하는 것이다. Prefix 처리 또는 assignment control flow가 수정되면 이 판단을 철회해야 한다.

XML importer는 file path를 stdout에 `print()`한다. OCEL 2.0 XML exporter는 없다.

---

## 11. 공개 출력 API

확인된 exporter는 classic JSON-OCEL 하나다.

```python
from ocpa.objects.log.exporter.ocel import factory

factory.apply(
    ocel,
    file_path,
    variant="ocel_json",
)
```

Exporter가 읽는 내부 source는 다음으로 제한된다.

```text
ocel.obj.meta
ocel.obj.raw.events
ocel.obj.raw.objects
```

출력은 version `"1.0"`과 timestamp ordering을 선언한다.

Exporter가 사용하지 않는 top-level field는 다음과 같다.

```text
ocel.log
ocel.graph
ocel.o2o_graph
ocel.change_table
```

따라서 OCEL 2.0 importer로 만든 composite를 classic JSON exporter에 전달하면 O2O, object change, E2O qualifier가 출력되지 않는다.

CSV, XML, SQLite, OCEL 2.0 JSON, bundle exporter는 확인되지 않았다.

---

## 12. Import·Export 중 Normalization과 Mutation

확인된 normalization 또는 mutation은 다음과 같다.

### 12.1 CSV

- source event ID 대신 sequential string ID 생성
- timestamp를 Pandas datetime으로 변환
- timestamp 기준 sort
- 누락된 start timestamp를 completion timestamp로 대체

### 12.2 Classic JSON

- source event dictionary key 대신 sequential integer ID 생성
- trailing `Z` 제거 후 timestamp parsing
- 누락된 `start_timestamp`를 추가
- event/object dictionary를 DataFrame과 graph로 중복 materialize

### 12.3 DataFrame converter

- 입력 DataFrame을 `event_timestamp` 기준으로 in-place sort
- event ID를 1부터 다시 생성하는 entity representation 구성
- object type column을 non-`event_` column 이름으로 추론

이에 따라 `Table`의 event ID와 `ObjectCentricEventLog`의 event ID가 importer path에 따라 같은 type과 numbering을 가진다고 일반화할 수 없다.

### 12.4 Lazy calculation

- variant 계산이 `event_variant` column을 Table에 추가
- process execution과 variant cache를 OCEL instance에 저장

### 12.5 Export

- Timestamp를 `isoformat()` string으로 변환
- `default=str`로 JSON 직렬화
- classic version `"1.0"`을 새로 선언

공통 mutation 또는 loss report는 없다.

---

## 13. Relation 표현과 보존

### 13.1 E2O

E2O는 representation마다 다르게 나타난다.

```text
Table:
    object type별 event column의 object ID list

ObjectCentricEventLog:
    Event.omap
    RawObjectCentricData.obj_event_mapping

EventGraph:
    동일 object를 공유하는 event 사이의 directly-following edge
```

### 13.2 E2O qualifier

Classic JSON과 CSV에는 qualifier 표현이 없다. OCEL 2.0 SQLite/XML importer는 qualifier를 event node attribute dictionary로 전달하지만 dedicated relation object로 유지하지 않는다.

### 13.3 O2O

OCEL 2.0 SQLite/XML importer만 `ObjectGraph`로 구성한다. Classic JSON exporter는 이를 쓰지 않는다.

### 13.4 Object change

OCEL 2.0 SQLite/XML importer만 `ObjectChangeTable`로 구성한다. Classic JSON exporter는 이를 쓰지 않는다.

### 13.5 E2E

Top-level `OCEL`, importer, exporter에 E2E field 또는 file mapping이 없다. 검사한 I/O surface에서 E2E round trip은 지원되지 않는다.

---

## 14. Format별 보존 행렬

| Format 경로 | Event ID | Event attr | Object attr | E2O | E2O qualifier | O2O | Object change | E2E |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSV import | Table 0-based / entity 1-based 재생성 | 예 | 선택적 별도 table | 예 | 아니오 | 아니오 | 아니오 | 아니오 |
| Classic JSON import | 재생성 | 예 | Entity representation에 예 | 예 | 아니오 | 아니오 | 아니오 | 아니오 |
| Classic JSON export | 내부 ID 출력 | 예 | 예 | 예 | 아니오 | 아니오 | 아니오 | 아니오 |
| Classic XML import | numeric 변환 | 예 | DataFrame 반환 시 예 | 예 | 아니오 | 아니오 | 아니오 | 아니오 |
| OCEL 2.0 SQLite import | Table/graph source ID, entity 1-based 재생성 | 예 | change table 중심 | 예 | EventGraph node attribute | 예 | 예 | 아니오 |
| OCEL 2.0 XML import | Table/graph source ID, entity 1-based 재생성 | source-level 위험 있음 | change table 중심 | 예 | EventGraph node attribute | 예 | 예 | 아니오 |

“예”는 명시적인 source path를 확인했다는 뜻이다. 모든 primitive type과 malformed input에 대한 semantic equality를 입증하지 않는다.

Classic JSON round trip도 identity-preserving이라고 볼 수 없다.

```text
external event ID 재생성
+ trailing Z normalization
+ synthetic start_timestamp 가능
= byte/semantic identity 미보장
```

---

## 15. 주요 위험과 모호성

1. **복수 representation 불일치** — Table, entity dictionary, graph를 동시에 보관하지만 공통 invariant validator가 없다.
2. **Event ID 재생성과 ID-space 불일치** — CSV와 classic JSON import가 source event identity를 바꾸며, 일부 path는 composite representation마다 다른 ID를 사용한다.
3. **Qualifier의 비정규화된 보존** — OCEL 2.0 qualifier가 typed relation이 아니라 graph node attribute로 들어간다.
4. **OCEL 2.0의 lossy export** — 유일한 exporter가 classic JSON 1.0만 쓰므로 O2O와 change를 잃는다.
5. **Classic XML surface 불완전** — factory surface가 있지만 composite OCEL 반환은 지원되지 않는다.
6. **Event attribute parser 위험** — OCEL 2.0 XML의 declared attribute branch에서 assignment 누락 가능성이 있다.
7. **Mutable default parameter** — SQLite importer 호출 사이에 default dictionary가 공유될 수 있다.
8. **Synthetic data** — 누락된 start timestamp를 자동 추가한다.
9. **Timezone 의미 변화** — classic JSON의 trailing `Z` 제거가 timezone-aware identity를 보존하지 않을 수 있다.
10. **E2E 부재** — in-memory 및 file I/O contract에 E2E가 없다.
11. **Loss report 부재** — dropped, regenerated, inferred, coerced component를 공통 result로 제공하지 않는다.
12. **Runtime 검증 부재** — 현재 환경에서 importer/exporter test를 실행하지 못했다.

---

## 16. PIX에 대한 예비 시사점

### 16.1 참조할 가치가 있는 패턴

- Tabular view와 entity view를 분리하는 발상
- Object-sharing 기반 EventGraph
- O2O graph의 explicit representation
- Object type별 change table
- Connected-component와 leading-object process execution
- 실제 classic JSON 및 OCEL 2.0 sample log

### 16.2 PIX에서 재설계가 필요한 패턴

- 하나의 mutable composite에 여러 canonical-like representation 보관
- Source event ID 재생성
- Query 시 내부 state mutation
- Dedicated E2O relation contract 부재
- Qualifier의 graph attribute 저장
- Import/export loss report 부재
- Classic/OCEL 2.0 version의 비대칭 surface
- Empty, invalid, unsupported, unavailable 상태 미구분
- E2E 미지원

### 16.3 PIX adapter result 후보

```text
DatasetImportResult
├── dataset
├── source_format
├── source_format_version
├── identifier_mapping
├── normalized_fields
├── synthetic_fields
├── rejected_records
├── inferred_records
├── unavailable_components
├── assumptions
└── source references
```

특히 source event ID를 변경해야 한다면 `identifier_mapping`이 필요하다. O2O, object change, E2E를 지원하지 않는 target으로 export할 경우 `omitted_components`와 `lossy_conversions`를 명시해야 한다.

이 shape은 예비 설계 후보이며 승인된 PIX contract가 아니다.

---

## 17. 미확인 사항

다음은 현재 source 검사만으로는 **알 수 없음**이다.

- 모든 sample log의 실제 import 성공 여부
- Classic JSON import→export의 정확한 semantic diff
- OCEL 2.0 SQLite/XML qualifier를 downstream algorithm이 실제 사용하는 정도
- Declared XML event attribute 누락 위험의 runtime 재현 여부
- Object change의 base value와 update value 구분 정확성
- Timezone-aware timestamp의 전체 format별 보존
- Duplicate event/object ID behavior
- Dangling E2O/O2O reference behavior
- 대규모 dataset의 memory overhead
- Multiple representation 사이의 drift 빈도
- OCPA가 의도하는 authoritative OCEL representation

---

## 18. 유효기간과 철회 조건

이 분석은 다음 commit에 유효하다.

```text
de056e0203a3fa4a9bbc19a95e001eada323074a
```

다음 경우 관련 판단을 재검토하거나 철회한다.

- OCPA가 canonical immutable OCEL model을 도입한 경우
- Representation consistency validator가 추가된 경우
- Source event ID를 보존하는 importer가 도입된 경우
- OCEL 2.0 JSON 또는 export path가 추가된 경우
- Dedicated E2O relation/qualifier contract가 추가된 경우
- E2E import/export가 추가된 경우
- Classic XML이 composite `OCEL`을 반환하게 된 경우
- XML event attribute runtime test가 source-derived 위험을 반증한 경우
- Round-trip test가 현재 보존 행렬을 반증한 경우
- PIX의 canonical dataset requirement가 변경된 경우

---

## 19. 최종 평가

**OCPA의 `OCEL`은 `Table + ObjectCentricEventLog + EventGraph`를 필수로 묶고 OCEL 2.0에서 `ObjectGraph + ObjectChangeTable`을 추가하는 mutable multi-representation composite다. 이 구조는 object-centric case, variant, discovery 계산에 편리하지만 representation consistency와 source identity 보존을 자동으로 보장하지 않는다. CSV와 classic JSON import는 event ID를 재생성하고 일부 path는 representation별로 다른 ID space를 만들며, classic XML은 composite OCEL 반환을 지원하지 않는다. SQLite에는 source event ID와 RangeIndex 사이 E2O alignment 실패 경로가 있고, XML event attribute는 일반적인 선언에서 lexical value를 남기되 declared type을 잃고 string으로 수렴한다. 유일한 classic JSON exporter는 OCEL 2.0의 qualifier·O2O·object change를 보존하지 않고 E2E와 공통 loss report도 없다. 따라서 PIX는 OCPA의 object-centric semantics와 projection algorithm을 참고할 수 있지만 I/O 및 dataset contract는 evidence-preserving 방식으로 재설계해야 한다.**

---

<!-- English version -->

# OCPA OCEL data model and file input and output analysis

**Document type:** Upstream reference analysis / OCEL data model and file I/O baseline

**Target project:** PIX

**Reference library:** OCPA

**Reference repository:** `https://github.com/ocpm/ocpa.git`

**Analysis branch:** `main`

**Analysis commit:** `de056e0203a3fa4a9bbc19a95e001eada323074a`

**OCPA Version:** `1.3.3`

**Analysis date:** 2026-07-23

**Status:** Source level OCEL data model and input-output Analysis baseline line

---

## 0. Purpose and scope

This document describes how OCPA configures the OCEL object, how CSV·classic JSON/XML·OCEL 2.0 reads SQLite/XML as the corresponding representation, and how to display it in what format.

The scope of analysis is as follows:

1. The highest `OCEL` composite dataclass
2. Table, entity dictionary, EventGraph representation
3. The O2O graph and the object-change table
4. Lazy process-execution and variant cache
5. Format by importer and exporter dispatch
6. Event/object ID, attribute, E2O, qualifier, O2O, object change, E2E storage
7. Normalization and mutation between import/export
8. Preliminary test point for PIX contract and adapter

This document is source-level analysis. It does not demonstrate runtime round-trip equality, processing volume, memory usage or complete compliance with the OCEL standard for all samples.

---

## 1. Analysis baseline

```text
Repository: ocpm/ocpa
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3
```

The main areas of examination are:

```text
ocpa/objects/log/ocel.py
ocpa/objects/log/variants/
ocpa/objects/log/converter/
ocpa/objects/log/importer/csv/
ocpa/objects/log/importer/ocel/
ocpa/objects/log/importer/ocel2/
ocpa/objects/log/exporter/ocel/
sample_logs/
tests/
```

In the current local Python environment, there is no pytest and runtime testing is not possible. Therefore, operations derived from the source without execution are classified as source-level observations in the document.

---

## 2. Complete object I/O architecture

OCPA converts one external log into several in-memory representations.

```text
외부 OCEL/CSV file
    ↓
format factory 또는 parser
    ↓
Pandas event table
    ├──→ Table
    ├──→ ObjectCentricEventLog
    └──→ EventGraph
            ↓
        OCPA OCEL
        ├── log
        ├── obj
        ├── graph
        ├── parameters
        ├── o2o_graph       # optional
        └── change_table    # optional
```

Classic JSON exporter does not serialize the entire composite. `ocel.obj`'s metadata and raw event/object dictionary are read and written in JSON-OCEL 1.0 form.

```text
OCPA OCEL
    ↓
ocel.obj.meta + ocel.obj.raw
    ↓
classic JSON-OCEL 1.0
```

Therefore, the scope of internal representation dealt with by the importer and the exporter is different.

---

## 3. OCEL data model

### 3.1 The highest `OCEL`

`ocpa.objects.log.ocel.OCEL` is the next mutable dataclass.

```python
@dataclass
class OCEL:
    log: Table
    obj: ObjectCentricEventLog
    graph: EventGraph
    parameters: dict
    o2o_graph: ObjectGraph = None
    change_table: ObjectChangeTable = None
```

The responsibilities of each field are as follows:

| Field | Type | Meaning |
| --- | --- | --- |
| `log` | `Table` | Event centered Pandas DataFrame and lookup cache |
| `obj` | `ObjectCentricEventLog` | Event·object entity dictionary and metadata |
| `graph` | `EventGraph` | Event ordering/object-sharing based directed graph |
| `parameters` | `dict` | Process execution, variant and import settings |
| `o2o_graph` | `ObjectGraph \| None` | OCEL 2.0 O2O directed graph |
| `change_table` | `ObjectChangeTable \| None` | Object type attribute-change DataFrame |

The `OCEL` constructor does not verify whether the three essential representations represent the same event/object/relation.

### 3.2 `Table`

`Table` copies the transmitted event DataFrame and sets `event_id` as an index.

```text
Table
├── _log                 # copied Pandas DataFrame
├── _object_types        # parameters["obj_names"]
├── _object_attributes
├── _numpy_log
├── _column_mapping
└── _mapping             # event ID → column value lookup
```

The customary column of the internal event table is as follows:

```text
event_id
event_activity
event_timestamp
event_start_timestamp
event_<attribute>
<object-type-1>          # 관련 object ID list/set
<object-type-2>
...
```

OCPA's E2O relation is expressed as an object-type event column rather than an independent relation table.

### 3.3 Entity representation

`ObjectCentricEventLog` links metadata to raw data.

```text
ObjectCentricEventLog
├── meta: MetaObjectCentricData
└── raw: RawObjectCentricData
    ├── events: dict[event_id, Event]
    ├── objects: dict[object_id, Obj]
    └── obj_event_mapping: dict[object_id, event_id list]
```

Entity shape is as follows:

```python
Event(
    id,
    act,
    time,
    omap,
    vmap,
)

Obj(
    id,
    type,
    ovmap,
)
```

`ObjectCentricEventLog.__post_init__()` immediately materializes the activity set, activity by event, object-type by object, event by object, object by timestamp-ordered sequence and activity trace.

### 3.4 EventGraph

`EventGraph` is a `nx.DiGraph` wrapper.

```python
@dataclass
class EventGraph:
    eog: nx.DiGraph
```

`eog_from_log()` connects events that share the same object by object type according to the timestamp-ordered table order. Add edge to the next event from the previous event for each object.

When the Qualifier dictionary is provided, it is set to the NetworkX node attribute. There is no separate typed E2O relation object or qualifier table.

### 3.5 ObjectGraph and ObjectChangeTable

OCEL 2.0 importer selectively adds the following representation.

```python
@dataclass
class ObjectGraph:
    graph: nx.DiGraph


@dataclass
class ObjectChangeTable:
    tables: dict[str, pd.DataFrame]
```

The O2O qualifier is stored as a graph edge attribute. Object change keeps the `object_id`, timestamp, changed-field indicator and value column in DataFrame for each object type.

### 3.6 Lazy process execution and variant

The next property is calculated at first access.

```text
process_executions
process_execution_objects
process_execution_mappings
variants
variant_frequencies
variant_graphs
variants_dict
```

The basic process execution method is connected component and the basic variant method is two-phase.

The variant calculation adds but removes the temporary `event_objects` column, and records the final `event_variant` column to `Table.log`. Thus read-like property access can change the internal DataFrame.

### 3.7 Mutability and complexity boundaries

OCPA `OCEL` is not an immutable dataset contract.

- You can replace the top-level dataclass field.
- You can change the public DataFrame of Table.
- Event, Obj, graph, change table are also mutable.
- Lazy calculation changes the cache and log column.
- `Table.remove_object_references()` is an in-place helper.
- Source comment states that the helper does not guarantee the consistency of all representations.

Therefore, the fact that `OCEL` was created alone does not show that Table, entity dictionary, EventGraph, O2O graph, change table match each other.

---

## 4. API public input

OCPA does not have a single `read_ocel2()` facade that routes all OCEL formats automatically as an extension like PM4Py. Directly import the format family modules.

| Input | Calling surface | Returns |
| --- | --- | --- |
| CSV | `objects.log.importer.csv.factory.apply` | The basic `OCEL` |
| Classic JSON-OCEL | `objects.log.importer.ocel.factory.apply` | `OCEL` |
| Classic XML-OCEL | `variant="ocel_xml"` of the same factory | DataFrame or tuple when `return_df=True` |
| OCEL 2.0 SQLite | `objects.log.importer.ocel2.sqlite.factory.apply` | `OCEL` |
| OCEL 2.0 XML | `objects.log.importer.ocel2.xml.factory.apply` | `OCEL` |

The verified importer does not have a OCEL 2.0 standard JSON, GZIP JSON/XML or Parquet bundle path.

---

## 5. Common Import Processing

Detailed implementations vary by format, but generally make the following representation.

```text
external records
→ event DataFrame
→ object type별 related-object column
→ Table
→ Event/Obj dictionary
→ ObjectCentricEventLog
→ EventGraph
→ optional ObjectGraph/ObjectChangeTable
→ OCEL
```

There is no common structured import result. The Importer does not report the following as a field.

- normalized field
- regenerated identifier
- rejected record
- inferred record
- unsupported component
- lossy conversion
- assumption
- source record reference

---

## 6. CSV Import

### 6.1 Type of input

CSV event table specifies column meaning as a parameter.

```python
parameters = {
    "obj_names": ["application", "offer"],
    "val_names": [],
    "act_name": "event_activity",
    "time_name": "event_timestamp",
    "sep": ",",
}
```

The cell in the object type column parses to an object ID list or set-form string.

### 6.2 Variant

CSV factory offers the following variant.

```text
to_df
to_obj
to_ocel       # default
```

`to_ocel` is a combination of `to_df`, `Table`, `df_to_ocel`, and `eog_from_log`.

### 6.3 Identifier and timestamp

`to_df` creates the next ID based on the row position above the source code, even if the input has an event ID.

```python
event_id = [str(i) for i in range(len(df))]
```

When making `ObjectCentricEventLog` with this DataFrame, `df_to_ocel` again enumerates an event from 1. Therefore, even within the same CSV import results, the 0-based ID of `Table`·`EventGraph` and the 1-based ID of entity representation may differ.

Timestamp converts to Pandas datetime and sorts the event table according to the timestamp. If there is no start timestamp parameter, the completion timestamp is copied to `event_start_timestamp`.

### 6.4 Preservation limits

CSV importer represents the following:

- Event activity and timestamp
- event attribute
- E2O reference by object type
- Selective object attribute table

The following support path has not been confirmed.

- E2O qualifier
- O2O relation
- object change history
- E2E relation

There is no CSV exporter.

---

## 7. Classic JSON-OCEL Import

### 7.1 External representation

Classic JSON importer uses the following key:

```text
ocel:global-log
ocel:events
ocel:objects
ocel:activity
ocel:timestamp
ocel:omap
ocel:vmap
ocel:type
ocel:ovmap
```

### 7.2 Parsing

```text
JSON dictionary
→ parse_events
→ parse_objects
→ MetaObjectCentricData
→ RawObjectCentricData
→ ObjectCentricEventLog
→ jsonocel_to_csv
→ Table + EventGraph
→ OCEL
```

### 7.3 Re-allocate the event ID

`parse_events()` does not preserve the event dictionary key of JSON as an internal ID and assigns `0, 1, 2, ...` according to the iteration sequence.

```text
external event key → internal sequential integer ID
```

`Event.id` type annotation is a string, but in this path an integer enters. Python dataclass is allowed because it does not impose a runtime type.

### 7.4 Timestamp and synthetic attribute

When the timestamp ends with `Z`, `Z` is removed and `datetime.fromisoformat()` is called. In this case it can be naive datetime without explicit UTC timezone information.

If `vmap` does not have `start_timestamp`, the event timestamp is used to add synthetic `start_timestamp`. Since then classic JSON export has been able to write this enhanced value to `vmap`.

### 7.5 Object attribute and representation difference

Raw `Obj.ovmap` maintains the JSON object attribute. However, the object returned by the JSON-to-CSV converter DataFrame is currently empty and the importer resets it to `None`. As a result, entity representation may have an attribute, but `Table`'s object-attribute lookup representation may not.

In addition, the public classic JSON factory receives the `file_path_object_attribute_table` argument, but when a selected importer is called, it does not transmit the corresponding value, but it fixes and passes the `None`. Therefore, separate object-attribute table inputs via factory surface are not actually applied.

### 7.6 Known source comment

Source comment states that a downstream alignment error may be propagated as the object type, which is not declared in global metadata but not referenced in any event, does not appear in the DataFrame column.

Also, for the expression that constitutes `val_names` of the Table parameter, source TODO directly indicates — incorrectly concatenated — . Therefore, it should not be assumed that the classic JSON event attribute is exposed with the same name in the entity view and Table view.

---

## 8. Classic XML-OCEL Import

The Classic XML variant looks like a `OCEL` importer in its name and type annotation, but the actual source operates as follows:

```text
return_df=True
→ event DataFrame
→ object DataFrame 또는 event DataFrame만 반환

return_df=False
→ ValueError(
    "Returning ocel from xml is not supported yet. Use return_df=True."
  )
```

Therefore, routes directly converging from classic XML to OCPA composite `OCEL` are not currently supported.

Additional characteristics are as follows:

- Parsing event and object attributes according to the XML tag type.
- Convert `omap` to an object type event column.
- `event_id` is converted to float, then int, assuming a numeric-castable ID.
- There is no classic XML exporter.

---

## 9. OCEL 2.0 SQLite Import

### 9.1 Reading table

Importer then uses the OCEL 2.0 relational table.

```text
event
object
event_map_type
object_map_type
event_<event-type>
object_<object-type>
event_object
object_object
```

### 9.2 Event reconstruction

The `event` table merges the type-specific event table by default. Type-specific timestamp column is combined into one `event_timestamp` and the event attribute column is assigned the `event_` prefix.

`Table` and `EventGraph` use the source event ID of SQLite. However, the `ObjectCentricEventLog` generated together passes the `df_to_ocel` and enumerates the event from 1 again. Therefore, a source-ID graph/table and a regenerated-ID entity view can coexist within a composite.

### 9.3 E2O and qualifier

`event_object` and `object` are joined to form an event-specific object type column.

The qualifier reads to the next dictionary.

```text
event_id
└── object_id → qualifier
```

This dictionary is forwarded to `eog_from_log()` and set to the EventGraph node attribute. Dedicated E2O relation table is not left on the final `OCEL`.

### 9.4 O2O

`object_object` is converted to `nx.DiGraph`.

```text
source object → target object
edge attribute: qualifier
```

### 9.5 Object change

`object_map_type` searches for a type-specific object table and stores the object type-specific DataFrame dictionary in `ObjectChangeTable`.

### 9.6 Source-level risk

Factory and implementation use `parameters={}`, a mutable default argument, and the importer adds `obj_names` to the dictionary if needed. The possibility of default parameter state sharing between multiple calls is a source-level risk that requires runtime testing.

The index of frames that aggregate `event_object` by object type is the source event ID. On the other hand, the update subject `event_df` is the default RangeIndex Status that does not set the source event ID to index.

```text
aggregated_data index:
    e1, e2, ...

event_df index:
    0, 1, ...

event_df.update(aggregated_data[object_type])
```

Therefore, in string event ID, object reference may not be reflected in the event table due to Pandas index alignment. In a limited probe performed with Compatible current dependency, the object reference of a sample satisfying 24 relational constraints became zero without entity object, and `ValueError` occurred in the later debug sample helper.

OCPA's pinned Pandas 1.3.5 environment is not currently reproduced in Python, so the runtime exception itself is an auxiliary basis. However, it does not consider the E2O preservation of string event ID to be guaranteed until the source index is explicitly aligned or the pinned dependency probe contradicts it.

There is no SQLite exporter.

---

## 10. OCEL 2.0 XML Import

### 10.1 Parsing object

The Importer handles the next section.

```text
object-types
event-types
objects
events
```

### 10.2 Object and O2O

Mapping the object ID and type and making the object relationship `ObjectGraph` edge. The qualifier is stored as an edge attribute.

### 10.3 Object attribute change

The object attribute is collected as a change row by object type.

```text
object_id
attribute value column
chngfield
event_timestamp
```

`time="0"` is maintained as a string `"0"`, with the other values parsing as datetime. In the same timestamp column, string and datetime can be mixed.

### 10.4 Event and E2O qualifier

The event consists of `event_id`, `event_activity`, `event_timestamp`, object type related-object list. The E2O qualifier is transmitted through an event-by-event dictionary to the EventGraph node attribute, as with SQLite.

`Table` and `EventGraph` use the XML source event ID, but `ObjectCentricEventLog` creates a new 1-based ID from the DataFrame converter. Representation ID-space differences can occur, such as SQLite.

### 10.5 Event attribute processing risk

Parser first applies the XML prefix to the `event_` event attribute name, then checks the event-type declaration dictionary consisting of an unprefixed name.

```text
declaration key:
    pr_creator

lookup key:
    event_pr_creator
```

In a standard attribute name, the lookup fails and the `except` branch runs, so the lexical value itself is recorded in the `event_<name>` column. However, declared primitive type is not applied and is parsing as string fallback.

On the other hand, if the declaration name itself already contains the `event_` prefix and the lookup is successful, the attribute may be missing without a value assignment to the `try` branch.

Thus, the identified risk for the common OCEL 2.0 XML is that the declared attribute has a value remaining over the entire missing string, but loses the declared type and converges to the string. If the prefix processing or assignment control flow is corrected, this judgment should be withdrawn.

XML importer stdout the file path to `print()`. There is no OCEL 2.0 XML exporter.

---

## 11. Public release API

The verified exporter is a classic JSON-OCEL.

```python
from ocpa.objects.log.exporter.ocel import factory

factory.apply(
    ocel,
    file_path,
    variant="ocel_json",
)
```

The internal source read by the exporter is limited to:

```text
ocel.obj.meta
ocel.obj.raw.events
ocel.obj.raw.objects
```

The output declares version `"1.0"` and timestamp ordering.

The top-level fields that Exporter does not use are:

```text
ocel.log
ocel.graph
ocel.o2o_graph
ocel.change_table
```

Therefore, when a composite made with a OCEL 2.0 importer is delivered to a classic JSON exporter, the O2O, object change, E2O qualifier is not output.

CSV, XML, SQLite, OCEL 2.0 JSON, bundle exporter has not been confirmed.

---

## 12. Normalization and Mutation in Import-Export

The confirmed normalization or mutation is as follows:

### 12.1 CSV

- Create a sequential string ID instead of the source event ID.
- Convert the timestamp to Pandas datetime
- The timestamp standard sort
- Replace the missing start timestamp with the completion timestamp.

### 12.2 Classic JSON

- Instead of the source event dictionary key, create a sequential integer ID.
- After removing the trailing `Z` timestamp parsing
- Add the missing `start_timestamp`
- materialize the event/object dictionary with DataFrame and a graph

### 12.3 DataFrame converter

- Enter DataFrame by `event_timestamp` according to the in-place sort
- Create entity representation to recreate the event ID from 1
- Subject type column with non-`event_` column name

Accordingly, `Table`'s event ID and `ObjectCentricEventLog`'s event ID cannot be generalized to have the same type and numbering depending on the importer path.

### 12.4 Lazy calculation

- The variant calculation adds the `event_variant` column to the table
- Save the process execution and variant cache to the OCEL instance

### 12.5 Export

- Convert the timestamp to the `isoformat()` string
- `default=str` to JSON in linear form
- The classic version of `"1.0"` is declared new.

No common mutation or loss report.

---

## 13. Relation expression and preservation

### 13.1 E2O

E2O is represented differently by each representation.

```text
Table:
    object type별 event column의 object ID list

ObjectCentricEventLog:
    Event.omap
    RawObjectCentricData.obj_event_mapping

EventGraph:
    동일 object를 공유하는 event 사이의 directly-following edge
```

### 13.2 E2O qualifier

Classic JSON and CSV have no qualifier representation. OCEL 2.0 SQLite/XML importer passes the qualifier to the event node attribute dictionary but does not keep it as a dedicated relation object.

### 13.3 O2O

OCEL 2.0 SQLite/XML importer only consists of `ObjectGraph`. Classic JSON exporter does not use this.

### 13.4 Object change

OCEL 2.0 SQLite/XML importer only consists of `ObjectChangeTable`. Classic JSON exporter does not use this.

### 13.5 E2E

There is no E2E field or file mapping on top-level `OCEL`, importer, exporter. E2E round trips on the inspected I/O surface are not supported.

---

## 14. Format-specific storage matrix

| Format path | Event ID | Event attr | Object attr | E2O | E2O qualifier | O2O | Object change | E2E |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CSV import | Table 0-based / entity 1-based regeneration | Yes, I did. | Selective star table | Yes, I did. | No, you can't. | No, you can't. | No, you can't. | No, you can't. |
| Classic JSON import | Renewable | Yes, I did. | Yes to the entity representation. | Yes, I did. | No, you can't. | No, you can't. | No, you can't. | No, you can't. |
| Classic JSON export | The internal ID output | Yes, I did. | Yes, I did. | Yes, I did. | No, you can't. | No, you can't. | No, you can't. | No, you can't. |
| Classic XML import | numeric conversion | Yes, I did. | DataFrame return the yes | Yes, I did. | No, you can't. | No, you can't. | No, you can't. | No, you can't. |
| OCEL 2.0 SQLite import | Table/graph source ID, entity 1-based reproducibility | Yes, I did. | Change table center | Yes, I did. | EventGraph node attribute | Yes, I did. | Yes, I did. | No, you can't. |
| OCEL 2.0 XML import | Table/graph source ID, entity 1-based reproducibility | There is a source-level risk. | Change table center | Yes, I did. | EventGraph node attribute | Yes, I did. | Yes, I did. | No, you can't. |

It means that the source path has been specified. It does not prove semantic equality for all primitive types and malformed inputs.

Classic JSON round trips are not identity-preserving.

```text
external event ID 재생성
+ trailing Z normalization
+ synthetic start_timestamp 가능
= byte/semantic identity 미보장
```

---

## 15. Major risks and ambiguities

1.  — Table, entity dictionary, and graph hold simultaneously but have no common invariant validator.
2. **Event ID playback and ID-space inconsistency** — CSV and classic JSON import change the source event identity, and some paths use a different ID for each composite representation.
3.  — OCEL 2.0 qualifier enters the graph node attribute instead of the typed relation.
4. **OCEL 2.0's lossy export** — the only exporter uses the classic JSON 1.0 million so it loses O2O and change.
5. **Classic XML surface incomplete** — factory surface but composite OCEL return is not supported.
6. **Event attribute parser risk** — OCEL 2.0 XML has the possibility of assignment missing from the declared attribute branch.
7. **Mutable default parameter** — SQLite default dictionary may be shared between importer calls.
8. **Synthetic data** — automatically adds the missing start timestamp.
9. **Timezone meaning changes** — classic JSON's trailing `Z` removal may not preserve timezone-aware identity.
10.  — in-memory and file I/O contract has no E2E.
11. **Loss report absence** — does not provide a dropped, regenerated, inferred, coerced component as a common result.
12.  — failed to run the importer/exporter test in the current environment.

---

## 16. Preliminary checkpoint for the PIX

### 16.1 A pattern worth looking at

- The idea of separating the tabular view from the entity view
- EventGraph based on object-sharing
- The explicit representation of the O2O graph
- Change table by object type
- Connected component and leading-object process execution
- The real classic JSON and OCEL 2.0 sample log

### 16.2 PIX needs to redesign the pattern

- Keep multiple canonical-like representations in one mutable composite
- Source event ID can be replicated
- Query city internal state mutation
- Dedicated E2O relation contract absence
- Save the qualifier's graph attribute
- Import/export loss report missing
- Classic/OCEL 2.0 version has an asymmetrical surface
- Empty, invalid, unsupported, unavailable Status is missing
- E2E subsidy

### 16.3 PIX adapter result candidate

```text
DatasetImportResult
├── dataset
├── source_format
├── source_format_version
├── identifier_mapping
├── normalized_fields
├── synthetic_fields
├── rejected_records
├── inferred_records
├── unavailable_components
├── assumptions
└── source references
```

Especially if you need to change the source event ID, you need `identifier_mapping`. If you export O2O, object change, E2E to a target that does not support it, you must specify `omitted_components` and `lossy_conversions`.

This shape is a preliminary design candidate and not an approved PIX contract.

---

## 17. Uncertainties

The next one is **unknown** for current source checks.

- Whether the actual import success of all sample logs
- The exact semantic diff of the classic JSON import→export
- OCEL 2.0 SQLite/XML the degree to which the downstream algorithm actually uses the qualifier
- Declared XML event attribute Missing risk of runtime replay or not
- Accuracy between the base value of the object change and the update value
- Save the full format of the Timezone-aware timestamp
- Duplicate event/object ID behavior
- Dangling E2O/O2O reference behavior
- The memory overhead of a large dataset
- The drift frequency between multiple representations
- authoritative OCEL representation intended by OCPA

---

## 18. Validity and Withdrawal Conditions

This analysis is valid for the following commit.

```text
de056e0203a3fa4a9bbc19a95e001eada323074a
```

In the following cases, the relevant judgments shall be reviewed or withdrawn.

- OCPA has introduced the canonical immutable OCEL model.
- If a representation consistency validator is added,
- If an importer is introduced to store the source event ID,
- OCEL 2.0 JSON or if an export path is added
- If you add a dedicated E2O relation/qualifier contract
- If the E2E import/export is added,
- If the Classic XML is forced to return the composite `OCEL`
- XML event attribute runtime test refutes the source-derived risk
- If the round-trip test contradicts the current conservation matrix,
- If the canonical dataset requirement of PIX is changed

---

## 19. The final evaluation

**OCPAof `OCEL`Silver `Table + ObjectCentricEventLog + EventGraph`It is necessary to bind them. OCEL From 2.0. `ObjectGraph + ObjectChangeTable`It's a mutable multi-representation composite that adds. This structure is convenient for object-centric case, variant, and discovery calculations but does not automatically guarantee representation consistency and source identity preservation. CSV and classic JSON import reproduce event IDs and some paths create different ID space per representation, while classic XML does not support composite OCEL returns. SQLite has an E2O alignment failure path between the source event ID and RangeIndex, and the XML event attribute leaves a lexical value in the general declaration, losing the declared type and converging into a string. The only classic JSON exporter does not preserve the qualifier·O2O·object change of OCEL 2.0 and has no common loss report with E2E. Thus PIX can refer to OCPA's object-centric semantics and projection algorithm, but I/O and dataset contracts must be redesigned in an evidence-preserving manner.**
