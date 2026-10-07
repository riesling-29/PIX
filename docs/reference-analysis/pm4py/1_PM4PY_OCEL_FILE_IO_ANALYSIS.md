<!-- 한국어 버전 -->

# PM4Py OCEL 데이터 모델 및 파일 입력·출력 분석

**문서 유형:** Upstream 참조 분석 / OCEL 데이터 모델 및 파일 I/O 기준선

**대상 프로젝트:** PIX

**참조 라이브러리:** PM4Py

**참조 저장소:** `https://github.com/process-intelligence-solutions/pm4py.git`

**분석 브랜치:** `release`

**분석 커밋:** `3329bbcbadce8764f7df660fd88636c30793fbd0`

**PM4Py 버전:** `2.7.23.3`

**분석일:** 2026-07-19

**상태:** 소스 수준 OCEL 데이터 모델 및 입력·출력 분석 기준선

---

## 0. 목적과 범위

이 문서는 PM4Py가 OCEL 객체를 어떻게 정의하는지, 외부 OCEL 파일을 해당 in-memory representation으로 어떻게 읽는지, 그리고 그 representation을 다시 외부 파일로 어떻게 serialize하는지를 설명한다.

분석 범위는 다음과 같다.

1. `OCEL` class와 constructor
2. 공통 OCEL in-memory DataFrame 구조
3. Mutability, copy, equality 및 version 판별 동작
4. 공개 OCEL 1.x 및 OCEL 2.0 read/write API
5. Importer와 exporter dispatch
6. CSV, JSON, XML, SQLite 및 bundled CSV/Parquet 형식
7. Normalization과 relation-filter propagation
8. Round-trip 보존 한계
9. PIX contract와 adapter에 대한 예비 시사점

이 문서는 소스 구조 분석이다. 모든 dataset에 대한 runtime throughput, memory consumption 또는 완전한 표준 준수를 입증하지 않는다.

---

## 1. 분석 기준

```text
Repository: process-intelligence-solutions/pm4py
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

주요 검사 영역은 다음과 같다.

```text
pm4py/read.py
pm4py/write.py
pm4py/objects/ocel/obj.py
pm4py/objects/ocel/importer/
pm4py/objects/ocel/exporter/
pm4py/objects/ocel/util/
```

---

## 2. 전체 I/O 아키텍처

PM4Py는 공통 mutable `OCEL` 객체를 중심으로 format별 importer와 exporter를 사용한다.

```text
외부 OCEL 파일
    ↓
pm4py.read_ocel*()
    ↓
format importer dispatcher
    ↓
선택된 importer variant
    ↓
Pandas DataFrame 재구성
    ↓
PM4Py OCEL 객체
    ↓
process-mining operation
    ↓
pm4py.write_ocel*()
    ↓
format exporter dispatcher
    ↓
선택된 exporter variant
    ↓
외부 OCEL 파일
```

반복되는 구현 패턴은 다음과 같다.

```text
public API
→ importer.py / exporter.py
→ Variants(Enum)
→ variants/<implementation>.py
→ apply(...)
```

따라서 I/O layer는 하나의 범용 serializer라기보다 공통 in-memory model로 수렴하는 format adapter 집합이다.

---

## 3. OCEL 데이터 모델과 In-Memory 구조

PM4Py는 여러 Pandas DataFrame을 담는 mutable `OCEL` container로 객체 중심 event log를 표현한다.

```text
OCEL
├── events
├── objects
├── relations          # event-to-object, E2O
├── o2o                # object-to-object
├── e2e                # event-to-event
├── object_changes
├── globals
└── parameters
```

### 3.1 Class 정의와 constructor

실제 객체는 `pm4py.objects.ocel.obj.OCEL`에 일반 Python class로 정의되어 있다. `dataclass` 또는 event/object entity graph가 아니며, constructor가 여러 DataFrame과 metadata dictionary를 하나의 container에 결합한다.

```python
OCEL(
    events=None,
    objects=None,
    relations=None,
    globals=None,
    parameters=None,
    o2o=None,
    e2e=None,
    object_changes=None,
)
```

Constructor는 먼저 `parameters`에서 실제 column name을 해석한다. 전달되지 않은 table은 필요한 최소 column을 가진 empty DataFrame으로 생성한다. 전달된 DataFrame은 constructor에서 복사하지 않고 그대로 instance attribute에 할당한다.

기본 attribute와 최소 schema는 다음과 같다.

| OCEL attribute | 기본 최소 column | 의미 |
| --- | --- | --- |
| `events` | `ocel:eid`, `ocel:activity`, `ocel:timestamp` | Event와 event attribute |
| `objects` | `ocel:oid`, `ocel:type` | Object와 object attribute |
| `relations` | `ocel:eid`, `ocel:activity`, `ocel:timestamp`, `ocel:oid`, `ocel:type`, `ocel:qualifier` | E2O relation과 denormalized metadata |
| `o2o` | `ocel:oid`, `ocel:oid_2`, `ocel:qualifier` | O2O relation |
| `e2e` | `ocel:eid`, `ocel:eid_2`, `ocel:qualifier` | E2E relation |
| `object_changes` | `ocel:oid`, `ocel:type`, `ocel:timestamp`, `ocel:field` | 시간에 따른 object attribute change |
| `globals` | dictionary | Log-level metadata |
| `parameters` | dictionary | Column-name override 등 constructor 설정 |

`relations` 입력에 qualifier column이 없으면 constructor가 같은 길이의 `None` 값으로 `ocel:qualifier` column을 추가한다.

### 3.2 Event와 object

`events` DataFrame은 event identifier, activity/type, timestamp, event attribute를 포함한다. 기본 column은 다음과 같다.

```text
ocel:eid
ocel:activity
ocel:timestamp
```

`objects` DataFrame은 object identifier, object type, object attribute를 포함한다. 기본 column은 다음과 같다.

```text
ocel:oid
ocel:type
```

### 3.3 Event-object relation

내부 `relations` DataFrame은 denormalized되어 있다. 일반적으로 다음을 포함한다.

```text
event identifier
event activity
event timestamp
object identifier
object type
qualifier
```

일부 importer는 event table과 object table에서 activity, timestamp, object type을 조회해 relation에 다시 구성한다.

### 3.4 O2O, E2E, object change

`o2o`는 source object, target object, qualifier를 저장한다. `e2e`는 source event, target event, qualifier를 저장한다.

`object_changes`는 시간에 따라 변하는 attribute를 다음과 같이 표현한다.

```text
object identifier
object type
timestamp
changed field
해당 field 이름의 column에 있는 value
```

검사한 OCEL file importer 또는 exporter 중 `e2e`를 serialize하거나 재구성하는 것은 없었다. In-memory에 존재한다는 사실을 file round-trip 지원의 증거로 해석해서는 안 된다.

### 3.5 설정 가능한 column

`OCEL` 객체는 identifier, type, timestamp, qualifier, changed field에 사용할 실제 column name을 보관한다. Importer와 exporter parameter로 기본값을 바꿀 수 있다.

기본 column name은 다음 상수로 정의되어 있다.

```text
DEFAULT_EVENT_ID        = "ocel:eid"
DEFAULT_EVENT_ACTIVITY  = "ocel:activity"
DEFAULT_EVENT_TIMESTAMP = "ocel:timestamp"
DEFAULT_OBJECT_ID       = "ocel:oid"
DEFAULT_OBJECT_TYPE     = "ocel:type"
DEFAULT_QUALIFIER       = "ocel:qualifier"
DEFAULT_CHNGD_FIELD     = "ocel:field"
```

### 3.6 Mutability와 validation 경계

`OCEL`은 immutable contract가 아니다.

- `events`, `objects`, `relations` 등은 public mutable DataFrame이다.
- Constructor는 전달받은 DataFrame을 방어적으로 복사하지 않는다.
- 따라서 caller가 원본 DataFrame을 수정하거나 `ocel.events` 등을 직접 수정하면 OCEL 상태가 바뀐다.
- Constructor는 duplicate identifier, dangling relation, timestamp type 또는 필수 값의 의미적 정합성을 검증하지 않는다.
- 이러한 처리는 별도의 consistency, validation, filtering utility에 위임된다.

이 구조에서는 “객체가 생성됐다”는 사실이 “유효한 OCEL dataset이다”라는 뜻이 아니다.

`copy.copy(ocel)`과 `copy.deepcopy(ocel)`도 구분된다. `__copy__()`는 일부 핵심 table reference를 그대로 constructor에 전달하는 shallow semantics를 가지며, `__deepcopy__()`는 각 DataFrame과 metadata를 복사해 새 `OCEL`을 만든다. 따라서 mutation isolation이 필요하면 copy 경로를 명시적으로 선택하고 실제 shared reference 여부를 검증해야 한다.

### 3.7 Helper method와 OCEL 2.0 판별

객체가 직접 제공하는 주요 동작은 다음과 같다.

| Method | 동작 |
| --- | --- |
| `get_extended_table()` | Event table을 기준으로 object type별 관련 object ID list를 붙인 flat DataFrame 생성 |
| `get_summary()` | Event, object, activity, object type, E2O 수를 문자열로 요약 |
| `is_ocel20()` | O2O, object change 또는 non-null E2O qualifier 존재 여부로 OCEL 2.0 추정 |
| `__eq__()` | 설정 column name, 모든 DataFrame, globals, parameters의 equality 비교 |
| `__hash__()` | 주요 설정과 DataFrame string representation을 이용해 hash 생성 |

`is_ocel20()`은 다음 조건 중 하나가 참이면 true를 반환한다.

```text
len(o2o) > 0
or len(object_changes) > 0
or non-null relation qualifier가 하나 이상 존재
```

이 판별은 `e2e`를 검사하지 않으며 schema declaration이나 표준 version metadata를 검증하지 않는다. 따라서 편의적 heuristic이지 완전한 OCEL 2.0 conformance 판정은 아니다.

---

## 4. 공개 입력 API

### 4.1 Classic `read_ocel()`

```python
ocel = pm4py.read_ocel(file_path, objects_path=None)
```

Path를 해석한 다음 extension에 따라 dispatch한다.

| 확장자 | 선택 경로 |
| --- | --- |
| `.csv` | Classic Pandas CSV importer |
| `.jsonocel` | Classic JSON-OCEL importer |
| `.xmlocel` | Classic XML-OCEL importer |
| `.sqlite` | Classic Pandas SQLite importer |

HTTP 또는 HTTPS 입력에서는 공개 helper가 resource를 임시 local file로 내려받고 그 path를 선택된 importer에 전달한다.

### 4.2 명시적 `read_ocel2()`

```python
ocel = pm4py.read_ocel2(file_path)
```

다음 입력을 인식한다.

| 입력 | 선택 경로 |
| --- | --- |
| `.ocel.zip` | Bundled OCEL 2.0 importer |
| `ocel-meta.json`을 포함한 디렉터리 | 압축되지 않은 bundle importer |
| `.sqlite` | OCEL 2.0 SQLite importer |
| `.csv` | Compact OCEL 2.0 CSV importer |
| `.json`, `.jsonocel` | OCEL 2.0 standard JSON importer |
| `.xml`, `.xmlocel` | OCEL 2.0 XML importer |
| `.json.gz`, `.jsonocel.gz` | GZIP JSON importer |
| `.xml.gz`, `.xmlocel.gz` | GZIP XML importer |

JSON과 XML에서는 지원되는 backend가 설치되어 있으면 선택적 Rust 기반 importer를 선택하고, 그렇지 않으면 Python 구현을 사용한다.

`read_ocel()`과 `read_ocel2()`는 alias가 아니다. 서로 다른 variant를 선택하고 인식하는 외부 representation도 다르다.

---

## 5. 공통 Import 처리

Parser가 달라도 결과 경로는 일반적으로 다음과 같다.

```text
외부 representation parsing
→ event와 object record 추출
→ E2O relation 추출
→ 지원되는 경우 O2O와 object change 추출
→ Pandas DataFrame 생성
→ identifier와 timestamp normalize
→ E2O에 event/object metadata 추가
→ temporal table sort
→ OCEL(...) 생성
→ consistency 처리
→ 선택적으로 relation filtering 전파
```

### 5.1 Identifier와 timestamp normalization

Importer에 따라 PM4Py는 다음을 수행한다.

- numeric identifier를 string으로 변환
- 숫자형 `.0` suffix artifact 제거
- timestamp string을 datetime으로 parsing
- 임시 row index 추가
- timestamp와 원래 순서로 event와 relation sort
- 처리 후 임시 index 제거

### 5.2 Consistency 처리

`ocel_consistency.apply()`는 다음을 수행한다.

- 필수 identifier, activity, type field를 string으로 변환
- 처리 대상 필수 column에 null이 있는 row 제거
- 처리 대상 필수 column에 empty string이 있는 row 제거
- 중복 event 또는 object identifier warning
- 누락된 qualifier를 empty string으로 교체
- `OCEL`의 DataFrame을 in-place로 변경

Invalid row는 structured rejected-record result로 반환되지 않는다. In-memory log에서 사라질 수 있다.

### 5.3 Relation-filter propagation

여러 importer 경로는 유지된 relationship을 기준으로 event, object, E2O, O2O, E2E, object change filtering을 전파한다. 모든 importer가 동일한 post-processing sequence를 실행하는 것은 아니므로 선택한 variant 수준에서 동작을 확인해야 한다.

OCEL 2.0 Definition 2는 event가 object와 연결되지 않거나 object가 event와 연결되지 않은 경우를 허용한다. 그러나 `propagate_relations_filtering()`은 E2O가 비어 있으면 events, objects 및 나머지 component를 모두 empty로 만든다. E2O가 일부만 존재하는 경우에도 E2O에 나타나지 않은 event와 object를 제거한다.

JSON Schema를 만족하는 “disconnected event 1건 + disconnected object 1건” 최소 OCEL 2.0 JSON을 `read_ocel2()`로 읽은 runtime probe에서는 최종 `OCEL`의 event와 object가 모두 0건이 되는 동작이 재현됐다.

따라서 relation-filter propagation을 단순 consistency 보정으로만 볼 수 없다. Valid OCEL 2.0 record를 제거할 수 있는 semantic filtering이다. 이 helper가 disconnected record를 보존하도록 변경되거나 import path에서 호출되지 않게 되면 이 판단을 철회해야 한다.

---

## 6. Classic CSV

### 6.1 물리 representation

Classic CSV는 확장 event table과 선택적 별도 object table을 사용한다.

```text
events.csv
├── event ID
├── activity
├── timestamp
├── event attributes
├── ocel:type:<Order> = ['order-1', 'order-2']
└── ocel:type:<Item>  = ['item-1', 'item-2']

objects.csv                  # optional
├── object ID
├── object type
└── object attributes
```

### 6.2 Export

Exporter는 consistency와 relation filtering을 적용하고 `OCEL.get_extended_table()`을 호출한다. 관련 object ID를 event와 object type별로 묶어 extended table을 쓰고, 선택적으로 objects DataFrame도 쓴다.

### 6.3 Import

Importer는 두 CSV를 string으로 읽고 object-type column을 찾는다. `ast.literal_eval()`로 list 형태 cell 값을 parsing하고, object reference마다 E2O row 하나를 만든다. 선택적 objects file이 없으면 reference를 바탕으로 object를 추론한다.

### 6.4 보존 한계

Classic CSV는 다음을 안정적으로 보존하지 못한다.

- relation qualifier
- O2O relation
- object change
- E2E relation
- objects file이 없을 때 관계에서 참조되지 않은 object attribute

이는 완전한 OCEL persistence format이 아니라 flatten된 interchange representation이다.

---

## 7. Compact OCEL 2.0 CSV

### 7.1 물리 representation

Compact OCEL 2.0 CSV variant는 하나의 table에 여러 entity kind를 encode한다.

```text
id
activity
timestamp
event attribute columns...
ot:<object-type-1>
ot:<object-type-2>
...
```

`ot:*` column의 object reference에는 object identifier, relation qualifier, JSON으로 encode된 object attribute가 들어갈 수 있다.

### 7.2 Row 해석

| Row 형태 | 의미 |
| --- | --- |
| ID, activity, timestamp 존재 | Event와 E2O relationship |
| ID, activity, timestamp 모두 없음 | Object 선언 |
| timestamp가 있고 ID와 activity는 없음 | Object attribute/change row |
| activity가 설정된 `o2o` marker와 같음 | O2O relation row |

### 7.3 Import

Importer는 timestamp를 parsing하고 `ot:` column을 식별한다. Object reference를 분해하고 object type을 등록하며 event/E2O/O2O를 만든다. Object attribute를 수집해 첫 값을 object에 두고 이후 값을 `object_changes`에 배치한다. Primitive type을 추론하고 temporal table을 sort한 뒤 `OCEL`을 생성한다.

### 7.4 Export

Exporter는 event row, 아직 선언되지 않은 object의 declaration row, 특수 O2O row, timestamp가 있는 object-change row를 출력한다. Object attribute는 object reference 안에 compact JSON으로 들어갈 수 있다.

Classic CSV보다 더 많은 OCEL 2.0 semantics를 보존하지만, 의미 해석이 row-shape 분류와 PM4Py의 compact reference grammar에 의존한다.

---

## 8. JSON-OCEL

### 8.1 Classic JSON

Classic JSON은 namespace가 있는 dictionary-indexed structure를 사용한다.

```json
{
  "ocel:global-log": {},
  "ocel:global-event": {},
  "ocel:global-object": {},
  "ocel:objects": {
    "order-1": {
      "ocel:type": "Order",
      "ocel:ovmap": {}
    }
  },
  "ocel:events": {
    "event-1": {
      "ocel:activity": "Create Order",
      "ocel:timestamp": "2026-07-19T00:00:00Z",
      "ocel:vmap": {},
      "ocel:omap": ["order-1"]
    }
  }
}
```

Extended variant는 typed E2O relationship, qualifier, O2O, object change를 인식한다.

### 8.2 OCEL 2.0 standard JSON

명시적인 OCEL 2.0 경로는 다음 형태로 쓴다.

```json
{
  "objectTypes": [
    {"name": "Order", "attributes": []}
  ],
  "eventTypes": [
    {"name": "Create Order", "attributes": []}
  ],
  "objects": [
    {
      "id": "order-1",
      "type": "Order",
      "attributes": [],
      "relationships": []
    }
  ],
  "events": [
    {
      "id": "event-1",
      "type": "Create Order",
      "time": "2026-07-19T00:00:00Z",
      "attributes": [],
      "relationships": [
        {"objectId": "order-1", "qualifier": "created"}
      ]
    }
  ]
}
```

Object base value와 이후 change는 한 object의 timestamped attribute 반복으로 표현된다. Import는 첫 값을 `objects`에, 이후 값을 `object_changes`에 분리한다. Export는 이를 다시 합친다.

### 8.3 압축과 API 구분

OCEL 2.0 JSON 경로는 `.json.gz`, `.jsonocel.gz`를 지원한다.

`write_ocel_json()`과 `write_ocel2_json()`은 동일하지 않다.

- `write_ocel_json()`은 `OCEL.is_ocel20()`을 이용해 `CLASSIC` 또는 내부 `OCEL20` variant를 선택한다.
- `write_ocel2_json()`은 `OCEL20_STANDARD`를 명시적으로 선택한다.

---

## 9. XML-OCEL

OCEL 2.0 XML exporter는 standard JSON과 의미상 동등한 hierarchy를 쓴다.

```xml
<log>
  <object-types>...</object-types>
  <event-types>...</event-types>
  <objects>
    <object id="order-1" type="Order">
      <attributes>...</attributes>
      <objects>
        <relationship object-id="order-2" qualifier="parent"/>
      </objects>
    </object>
  </objects>
  <events>
    <event id="event-1" type="Create Order" time="...">
      <attributes>...</attributes>
      <objects>
        <relationship object-id="order-1" qualifier="created"/>
      </objects>
    </event>
  </events>
</log>
```

Exporter는 type declaration을 도출하고 base 및 timestamped object attribute를 쓰며 qualifier를 포함한 E2O/O2O relationship을 기록한다. Importer는 이를 DataFrame으로 되돌리고 typed value를 parsing하며 temporal data를 sort한 뒤 consistency/filtering을 적용한다.

명시적 OCEL 2.0 XML 경로는 `.xml.gz`, `.xmlocel.gz`를 지원한다.

---

## 10. SQLite

### 10.1 Classic SQLite

Classic Pandas variant는 세 DataFrame을 직접 쓴다.

```text
EVENTS
OBJECTS
RELATIONS
```

이 경로는 O2O, E2E, object change를 쓰지 않는다.

### 10.2 OCEL 2.0 SQLite

명시적 OCEL 2.0 variant는 다음 table을 사용한다.

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

`event`와 `object`는 ID를 논리적 type에 mapping한다. Type-map table은 논리적 type name을 물리적인 type별 table과 연결한다. 각 `event_<type>` table은 timestamp와 event attribute를 저장하고, 각 `object_<type>` table은 base value와 시간에 따른 change를 저장한다.

`event_object`는 E2O와 qualifier를, `object_object`는 O2O와 qualifier를 저장한다.

Import할 때 PM4Py는 type별 table을 읽어 합치고 object base row와 change row를 분리한다. Relationship table을 읽고 E2O에 activity/timestamp/object type을 추가하며 temporal data를 sort한 뒤 `OCEL`을 생성한다.

---

## 11. Bundled CSV/Parquet

### 11.1 물리 형태

Bundle은 `.ocel.zip` archive 또는 `ocel-meta.json`을 포함한 디렉터리일 수 있다. 기본 table format은 Parquet이며 CSV도 선택할 수 있다.

```text
bundle/
├── ocel-meta.json
├── events/
│   ├── event_<encoded-event-type>.parquet
│   └── ...
├── objects/
│   ├── object_<encoded-object-type>.parquet
│   └── ...
├── object_changes/
│   ├── object_changes_<encoded-object-type>.parquet
│   └── ...
└── relations/
    ├── e2o.parquet
    └── o2o.parquet
```

Type name에서 filename에 안전하지 않은 문자는 percent-encoding한다.

### 11.2 Metadata

`ocel-meta.json`은 다음을 기록한다.

```text
OCEL version
bundle format version
CSV 또는 Parquet storage format
event type → event table 및 attribute declaration
object type → object table, changes table 및 attribute declaration
E2O table path
O2O table path
```

### 11.3 Export와 import

Export는 event type별 table 하나, object type별 base table과 changes table 하나, 별도의 E2O/O2O table, path와 primitive type을 설명하는 metadata를 만든다. File은 ZIP archive 또는 directory에 기록한다.

Import는 metadata를 읽고 선언된 모든 table을 load한다. Type별 frame을 concatenate하고 E2O metadata를 재구성하며 ID/timestamp를 normalize하고 temporal data를 sort한 뒤 `OCEL`을 생성한다.

Bundle은 검사한 representation 중 가장 dataset 중심적이며 typed columnar Parquet storage를 지원한다.

---

## 12. 공개 출력 API

### 12.1 Classic `write_ocel()`

```python
pm4py.write_ocel(ocel, file_path, objects_path=None)
```

| 확장자 | 선택 경로 |
| --- | --- |
| `.csv` | Classic extended-table CSV |
| `.jsonocel` | Classic 또는 내부 OCEL20 JSON variant |
| `.xmlocel` | Classic XML variant |
| `.sqlite` | Classic Pandas SQLite variant |

### 12.2 명시적 `write_ocel2()`

```python
pm4py.write_ocel2(
    ocel,
    file_path,
    storage_format="parquet",
)
```

| 확장자 | 선택 경로 |
| --- | --- |
| `.ocel.zip` | Bundled CSV/Parquet |
| `.sqlite` | OCEL 2.0 SQLite |
| `.csv` | Compact OCEL 2.0 CSV |
| `.json`, `.jsonocel` | Standard OCEL 2.0 JSON |
| `.xml`, `.xmlocel` | OCEL 2.0 XML |
| JSON/XML `.gz` 형태 | 압축된 standard JSON/XML |

### 12.3 Version 추론

`OCEL.is_ocel20()`은 non-empty O2O table, non-empty object-changes table 또는 non-empty relation qualifier를 발견하면 true를 반환한다. Generic JSON 출력은 이 결과로 variant를 선택한다.

이 heuristic은 `e2e`를 검사하지 않으며 완전한 표준 version validator가 아니다.

---

## 13. Export 시 Normalization과 Mutation

여러 exporter는 다음을 실행한다.

```text
input OCEL
→ ocel_consistency.apply()
→ propagate_relations_filtering()
→ format conversion
→ file write
```

Consistency와 filtering은 전달된 `OCEL`이 보유한 DataFrame을 교체하거나 filter할 수 있다. 따라서 exporter 호출이 caller에게 보이는 상태를 바꿀 수 있다.

가능한 변경은 다음과 같다.

- 필수 값이 invalid인 row 삭제
- identifier와 type을 string으로 변환
- null qualifier 교체
- relation에 유지되지 않는 event 또는 object filtering
- endpoint가 없는 O2O, E2E, object-change row filtering

모든 exporter가 같은 sequence를 수행하는 것은 아니다. Mutation 위험은 variant별로 평가해야 한다. 어떤 input record가 변경 또는 제거되었는지 보고하는 공통 result는 없다.

---

## 14. Round-Trip 보존 행렬

| 형식 | E2O | E2O qualifier | O2O | Object change | E2E |
| --- | ---: | ---: | ---: | ---: | ---: |
| Classic extended CSV | 일부 | 안정적인 보존 없음 | 아니오 | 아니오 | 아니오 |
| Classic SQLite | 예 | Schema column에 의존 | 아니오 | 아니오 | 아니오 |
| Classic JSON/XML | 예 | Variant에 의존 | Extended variant에 의존 | Extended variant에 의존 | 아니오 |
| Compact OCEL 2.0 CSV | 예 | 예 | 예 | 예 | 아니오 |
| Standard OCEL 2.0 JSON | 예 | 예 | 예 | 예 | 아니오 |
| OCEL 2.0 XML | 예 | 예 | 예 | 예 | 아니오 |
| OCEL 2.0 SQLite | 예 | 예 | 예 | 예 | 아니오 |
| OCEL 2.0 bundle | 예 | 예 | 예 | 예 | 아니오 |

“예”는 명시적인 serialization 및 reconstruction 경로를 관찰했다는 뜻이다. 모든 data type 또는 malformed dataset에 대해 semantic round-trip equality를 입증하지는 않는다.

검사한 OCEL importer/exporter package 아래에서 `ocel.e2e`를 참조하는 코드는 발견하지 못했다.

E2E는 PM4Py in-memory extension이지만 검사한 OCEL 2.0 Specification Definition 2의 구성 요소는 아니다. 따라서 E2E file round trip 부재는 PM4Py 기능 한계이지만 그 자체로 OCEL 2.0 미준수 근거는 아니다.

---

## 15. 주요 위험과 모호성

1. **Format에 따른 손실** — classic CSV와 SQLite는 전체 in-memory 구조를 표현하지 않는다.
2. **조용한 normalization** — invalid row가 보고되지 않고 제거될 수 있다.
3. **Export 측 mutation** — write operation이 전달받은 object를 변경할 수 있다.
4. **암묵적 object 추론** — object table이 없는 classic CSV는 relation에서 object를 재구성한다.
5. **API family 모호성** — classic 함수와 명시적 OCEL 2.0 함수가 서로 다른 variant를 선택한다.
6. **동적 change column** — changed-field name과 value를 함께 해석해야 한다.
7. **Relation denormalization** — 중복된 event/object metadata가 서로 불일치할 수 있다.
8. **Loss report 부재** — dropped, inferred, coerced, unsupported data를 나열하는 공통 contract가 없다.

---

## 16. PIX에 대한 예비 시사점

### 16.1 참조할 가치가 있는 패턴

- Neutral internal model로 수렴하는 format adapter
- 명시적으로 분리된 classic 및 OCEL 2.0 variant
- Type별 relational 및 bundle layout
- 분리된 E2O, O2O, object-change representation
- GZIP과 Parquet storage profile

### 16.2 PIX에서 재설계가 필요한 패턴

- Import 중 destructive normalization
- Export 중 mutation
- Structured import/export result 부재
- 공통 loss declaration 부재
- E2E file round trip 부재
- 암묵적 schema-version 추론
- Discrepancy evidence가 없는 denormalized relation semantics

### 16.3 Adapter result 후보 형태

PIX import adapter는 `ProcessDataset`보다 많은 정보를 반환해야 할 수 있다.

```text
DatasetImportResult
├── dataset
├── source_format
├── source_format_version
├── normalized_fields
├── rejected_records
├── inferred_records
├── unavailable_components
├── assumptions
└── source references
```

Export adapter에는 다음이 필요할 수 있다.

```text
DatasetExportResult
├── target_format
├── target_format_version
├── written_components
├── omitted_components
├── lossy_conversions
├── assumptions
└── output artifact reference
```

이는 예비 설계 시사점이며 승인된 PIX contract가 아니다.

---

## 17. 미확인 사항

다음은 소스 검사만으로는 **알 수 없음**이다.

- 모든 primitive 및 timestamp type에 대한 정확한 round-trip equality
- Schumpeter 규모 OCEL volume에서의 performance
- 실용적으로 처리 가능한 최대 object와 relation 수
- Relation denormalization의 memory overhead
- Python importer와 선택적 Rust importer의 edge-case 동등성
- 모든 PM4Py extension의 완전한 표준 준수
- 모든 duplicate 또는 conflicting object attribute 사례의 동작
- 검사 범위 밖의 non-obvious external integration이 E2E를 serialize하는지 여부

---

## 18. 유효기간과 철회 조건

이 분석은 다음 PM4Py commit에 유효하다.

```text
3329bbcbadce8764f7df660fd88636c30793fbd0
```

다음 경우 관련 판단을 재검토하거나 철회한다.

- PM4Py가 공개 OCEL I/O API를 변경한 경우
- Importer/exporter가 E2E serialization을 추가한 경우
- Exporter가 명시적으로 non-mutating이 된 경우
- Consistency 처리가 structured rejected-record 정보를 반환하는 경우
- Classic CSV 또는 SQLite가 완전한 OCEL 2.0 semantics를 지원하는 경우
- Compact CSV convention 또는 bundle layout이 변경된 경우
- 실행한 round-trip test가 소스 기반 보존 행렬을 반증하는 경우
- 선택적 Rust backend가 실질적으로 다른 structure를 생성하는 경우
- PIX가 canonical data 또는 evidence-lineage requirement를 변경하는 경우

---

## 19. 최종 평가

**PM4Py의 `OCEL`은 event와 object entity를 개별 domain object로 구성한 graph가 아니라 E2O, O2O, E2E, object change를 포함한 여러 mutable Pandas DataFrame을 묶은 연산 중심 container다. Format별 importer와 exporter variant는 외부 OCEL file을 이 공통 객체로 수렴시킨다. 명시적 OCEL 2.0 JSON, XML, SQLite, compact CSV, bundle 경로는 classic CSV와 classic SQLite보다 E2O relationship, qualifier, O2O relationship, object change를 더 완전하게 보존한다. 그러나 객체 생성 자체는 dataset validity를 보장하지 않고, relation-filter propagation은 명세가 허용한 disconnected event와 object를 제거할 수 있다. 또한 검사한 file-I/O layer는 E2E relation을 round-trip하거나 normalization, rejected row, inferred data, mutation, semantic loss를 공통 형식으로 기록하지 않는다. E2E는 OCEL 2.0 Definition 2의 요구사항이 아니므로 해당 부재와 표준 준수 판정은 분리해야 한다.**

---

<!-- English version -->

# PM4Py OCEL data model and file input and output analysis

**Document type:** Upstream reference analysis / OCEL data model and file I/O baseline

**Target project:** PIX

**Reference library:** PM4Py

**Reference repository:** `https://github.com/process-intelligence-solutions/pm4py.git`

**Analysis branch:** `release`

**Analysis commit:** `3329bbcbadce8764f7df660fd88636c30793fbd0`

**PM4Py Version:** `2.7.23.3`

**Analysis date:** 2026-07-19

**Status:** Source level OCEL data model and input-output Analysis baseline line

---

## 0. Purpose and scope

This document describes how PM4Py defines a OCEL object, how an external OCEL file is read as a corresponding in-memory representation, and how to serialize that representation back to an external file.

The scope of analysis is as follows:

1. `OCEL` class and constructor
2. Common OCEL in-memory DataFrame structure
3. Mutability, copy, equality and version sorting behavior
4. OCEL 1.x and OCEL 2.0 read/write API
5. Importer and exporter dispatch
6. CSV, JSON, XML, SQLite and bundled in the CSV/Parquet format
7. Normalization and relation-filter propagation
8. Round-trip conservation limits
9. Preliminary test point for PIX contract and adapter

This document is a source structure analysis. It does not demonstrate runtime throughput, memory consumption or complete standard compliance for all dataset.

---

## 1. Analysis baseline

```text
Repository: process-intelligence-solutions/pm4py
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

The main areas of examination are:

```text
pm4py/read.py
pm4py/write.py
pm4py/objects/ocel/obj.py
pm4py/objects/ocel/importer/
pm4py/objects/ocel/exporter/
pm4py/objects/ocel/util/
```

---

## 2. The whole I/O architecture.

PM4Py uses a format-specific importer and exporter based on a common mutable `OCEL` object.

```text
외부 OCEL 파일
    ↓
pm4py.read_ocel*()
    ↓
format importer dispatcher
    ↓
선택된 importer variant
    ↓
Pandas DataFrame 재구성
    ↓
PM4Py OCEL 객체
    ↓
process-mining operation
    ↓
pm4py.write_ocel*()
    ↓
format exporter dispatcher
    ↓
선택된 exporter variant
    ↓
외부 OCEL 파일
```

The pattern of repeated implementation is as follows:

```text
public API
→ importer.py / exporter.py
→ Variants(Enum)
→ variants/<implementation>.py
→ apply(...)
```

Therefore, the I/O layer is a set of format adapters that converge into a common in-memory model rather than a single generic serializer.

---

## 3. OCEL data model and In-memory structure

PM4Py represents the object-centered event log as a mutable `OCEL` container containing several Pandas DataFrame.

```text
OCEL
├── events
├── objects
├── relations          # event-to-object, E2O
├── o2o                # object-to-object
├── e2e                # event-to-event
├── object_changes
├── globals
└── parameters
```

### 3.1 Class definition and constructor

The actual object is defined in `pm4py.objects.ocel.obj.OCEL` as the general Python class. `dataclass` is not an event/object entity graph, and the constructor combines multiple DataFrame and metadata dictionaries into one container.

```python
OCEL(
    events=None,
    objects=None,
    relations=None,
    globals=None,
    parameters=None,
    o2o=None,
    e2e=None,
    object_changes=None,
)
```

Constructor first interprets the actual column name from `parameters`. The untransferred table is generated as empty DataFrame with the minimum required column. The transmitted DataFrame is not copied from the constructor and is assigned to the instance attribute.

The basic attribute and minimum schema are as follows:

| OCEL attribute | The default minimum column | Meaning |
| --- | --- | --- |
| `events` | `ocel:eid`, `ocel:activity`, `ocel:timestamp` | Event and event attribute |
| `objects` | `ocel:oid`, `ocel:type` | Object and object attribute |
| `relations` | `ocel:eid`, `ocel:activity`, `ocel:timestamp`, `ocel:oid`, `ocel:type`, `ocel:qualifier` | E2O relation and denormalized metadata |
| `o2o` | `ocel:oid`, `ocel:oid_2`, `ocel:qualifier` | O2O relation |
| `e2e` | `ocel:eid`, `ocel:eid_2`, `ocel:qualifier` | E2E relation |
| `object_changes` | `ocel:oid`, `ocel:type`, `ocel:timestamp`, `ocel:field` | Change the object attribute over time |
| `globals` | dictionary | Log-level metadata |
| `parameters` | dictionary | Column-name override and so on |

If there is no qualifier column in the `relations` input, the constructor adds the `ocel:qualifier` column to the `None` value of the same length.

### 3.2 Event and object

`events` DataFrame includes an event identifier, activity/type, timestamp, and event attribute. The basic column is as follows:

```text
ocel:eid
ocel:activity
ocel:timestamp
```

`objects` DataFrame includes an object identifier, object type, and object attribute. The basic column is as follows:

```text
ocel:oid
ocel:type
```

### 3.3 Event-object relation

Internal `relations` DataFrame is denormalized. It generally includes:

```text
event identifier
event activity
event timestamp
object identifier
object type
qualifier
```

Some importers check activity, timestamp, and object type in the event table and object table and reconfigure to relation.

### 3.4 O2O, E2E, object change

`o2o` stores the source object, target object, and qualifier. `e2e` stores the source event, target event, and qualifier.

`object_changes` represents an attribute that changes over time as follows:

```text
object identifier
object type
timestamp
changed field
해당 field 이름의 column에 있는 value
```

No OCEL file importer or exporter has serialized or reconfigured `e2e`. The fact that it exists in-memory should not be interpreted as evidence of file round-trip support.

### 3.5 Setup column

`OCEL` objects store the actual column name to be used for identifier, type, timestamp, qualifier, changed field. Importer and exporter parameters can change the default value.

The default column name is defined as:

```text
DEFAULT_EVENT_ID        = "ocel:eid"
DEFAULT_EVENT_ACTIVITY  = "ocel:activity"
DEFAULT_EVENT_TIMESTAMP = "ocel:timestamp"
DEFAULT_OBJECT_ID       = "ocel:oid"
DEFAULT_OBJECT_TYPE     = "ocel:type"
DEFAULT_QUALIFIER       = "ocel:qualifier"
DEFAULT_CHNGD_FIELD     = "ocel:field"
```

### 3.6 Mutability and validation boundaries

`OCEL` is not an immutable contract.

- `events`, `objects`, and `relations` are publicly mutable DataFrame.
- Constructor does not copy DataFrame transmitted defensively.
- Therefore, if the caller modifies the original DataFrame or `ocel.events` etc. directly, the OCEL Status is changed.
- The constructor does not verify the meaningful completeness of a duplicate identifier, dangling relation, timestamp type or essential value.
- These processes are assigned to separate consistency, validation, and filtering utilities.

In this structure, the fact that a receptor is generated does not mean that a receptor is a OCEL dataset.

`copy.copy(ocel)` and `copy.deepcopy(ocel)` are also distinguished. `__copy__()` has shallow semantics that convey some of the core table references directly to the constructor, while `__deepcopy__()` copies each DataFrame and metadata to create a new `OCEL`. Therefore, if mutation isolation is required, copy paths should be explicitly selected and verified for actual shared reference.

### 3.7 Helper method and OCEL 2.0 classification

The main actions provided by the object itself are as follows:

| Method | The action. |
| --- | --- |
| `get_extended_table()` | Create a flat DataFrame with an object ID list for each object type based on the event table |
| `get_summary()` | Summarize the event, object, activity, object type, E2O numbers in a string. |
| `is_ocel20()` | OCEL 2.0 estimates whether there is an O2O, object change or non-null E2O qualifier |
| `__eq__()` | Set the column name, all DataFrame, globals, equality comparison of parameters |
| `__hash__()` | Use the main settings and DataFrame string representation to generate hash. |

`is_ocel20()` returns true if one of the following conditions is true.

```text
len(o2o) > 0
or len(object_changes) > 0
or non-null relation qualifier가 하나 이상 존재
```

This classification does not check `e2e` or verify schema declaration or standard version metadata. Therefore a convenient heuristic is not a complete OCEL 2.0 conformance judgment.

---

## 4. API public input

### 4.1 Classic `read_ocel()`

```python
ocel = pm4py.read_ocel(file_path, objects_path=None)
```

Interpret the path and then dispatch it according to the extension.

| Expanders | The path of choice. |
| --- | --- |
| `.csv` | Classic Pandas CSV importer |
| `.jsonocel` | Classic JSON-OCEL importer |
| `.xmlocel` | Classic XML-OCEL importer |
| `.sqlite` | Classic Pandas SQLite importer |

In HTTP or HTTPS input, a public helper downloads a resource to a temporary local file and redirects the path to the selected importer.

### 4.2 explicit `read_ocel2()`

```python
ocel = pm4py.read_ocel2(file_path)
```

Recognize the next input.

| Input | The path of choice. |
| --- | --- |
| `.ocel.zip` | Bundled OCEL 2.0 importer |
| Directory including `ocel-meta.json` | Uncompressed bundle importer |
| `.sqlite` | OCEL 2.0 SQLite importer |
| `.csv` | Compact OCEL 2.0 CSV importer |
| `.json`, `.jsonocel` | OCEL 2.0 standard JSON importer |
| `.xml`, `.xmlocel` | OCEL 2.0 XML importer |
| `.json.gz`, `.jsonocel.gz` | GZIP JSON importer |
| `.xml.gz`, `.xmlocel.gz` | GZIP XML importer |

In JSON and XML, if a supported backend is installed, an optional Rust-based importer is selected, and otherwise the Python implementation is used.

`read_ocel()` and `read_ocel2()` are not aliases. The external representation that selects and recognizes different variants is also different.

---

## 5. Common Import Processing

The resulting paths are usually as follows, regardless of parser.

```text
외부 representation parsing
→ event와 object record 추출
→ E2O relation 추출
→ 지원되는 경우 O2O와 object change 추출
→ Pandas DataFrame 생성
→ identifier와 timestamp normalize
→ E2O에 event/object metadata 추가
→ temporal table sort
→ OCEL(...) 생성
→ consistency 처리
→ 선택적으로 relation filtering 전파
```

### 5.1 Identifier and timestamp normalization

According to the Importer, PM4Py performs the following:

- Convert the numeric identifier to string.
- Numerical `.0` suffix artifact removed
- Parsing the timestamp string to datetime
- Temporary row index added
- Timestamp and in the original order event and relation sort
- Remove the temporary index after processing

### 5.2 Consistency processing

`ocel_consistency.apply()` performs the following:

- Convert the required identifier, activity, type field to string
- Remove the null row in the required column of the treated object.
- Remove rows with empty strings from the required column to be processed.
- Reverse event or object identifier warning
- Replace the missing qualifier with an empty string.
- Change the DataFrame from `OCEL` to in-place

Invalid row is not returned as structured rejected-record result. It can disappear from the in-memory log.

### 5.3 Relation-filter propagation

Several importer routes propagate event, object, E2O, O2O, E2E, object change filtering based on the relationship maintained. Not all importers run the same post-processing sequence, so they must verify the operation at the selected variant level.

OCEL 2.0 Definition 2 allows if an event is not connected to an object or an object is not connected to an event. However, when E2O is empty, `propagate_relations_filtering()` makes all events, objects and the rest of the component empty. E2O removes events and objects that do not appear in E2O even if they are only partial.

A runtime probe that satisfies the JSON Schema with — disconnected event 1 — + disconnected object 1 — at least OCEL 2.0 read JSON as `read_ocel2()` in which the operation of the final `OCEL` event and object is both zero is reproduced.

Therefore, relation-filter propagation cannot be seen as simply a correction of consistency. Valid OCEL 2.0 is a semantic filtering that can remove a record. If this helper is changed to preserve the disconnected record or is not called from the import path, this judgment must be withdrawn.

---

## 6. Classic CSV

### 6.1 Physical representation

Classic CSV uses an expanded event table and an optional stellar object table.

```text
events.csv
├── event ID
├── activity
├── timestamp
├── event attributes
├── ocel:type:<Order> = ['order-1', 'order-2']
└── ocel:type:<Item>  = ['item-1', 'item-2']

objects.csv                  # optional
├── object ID
├── object type
└── object attributes
```

### 6.2 Export

The exporter applies consistency and relation filtering and calls `OCEL.get_extended_table()`. Link the relevant object ID by event and object type using an extended table, and optionally using objects DataFrame.

### 6.3 Import

The importer reads the two CSVs in a string to find the object-type column. `ast.literal_eval()` parsing the list form cell value, creating one row of E2O for each object reference. In the absence of an optional objects file, an object is inferred based on a reference.

### 6.4 Preservation limits

Classic CSV does not safeguard the following:

- relation qualifier
- O2O relation
- object change
- E2E relation
- The object attribute not referenced in the relationship when there is no objects file

This is not a complete OCEL persistence format, but a flattened interchange representation.

---

## 7. Compact OCEL 2.0 CSV

### 7.1 Physical representation

Compact OCEL 2.0 CSV variant encodes several entity types on one table.

```text
id
activity
timestamp
event attribute columns...
ot:<object-type-1>
ot:<object-type-2>
...
```

The object reference of the `ot:*` column may include an object attribute encoded as object identifier, relation qualifier, JSON.

### 7.2 Row interpretation

| Row shape | Meaning |
| --- | --- |
| ID, activity, timestamp existence | Event and E2O relationship |
| No ID, no activity, no timestamp at all. | Object declaration |
| There's a timestamp and no ID and no activity. | Object attribute/change row |
| The same as the `o2o` marker where the activity is set | O2O relation row |

### 7.3 Import

The Importer parses the timestamp and identifies the `ot:` column. Break down the object reference and register the object type to create an event/E2O/O2O. Collect the object attribute and place the first value on the object and then place the value on `object_changes`. After deducing the primitive type and sorting the temporal table, `OCEL` is generated.

### 7.4 Export

Exporter issues an event row, a declaration row for an undeclared object, a special O2O row, and an object-change row with a timestamp. The object attribute can be entered into a compact JSON within the object reference.

While more OCEL 2.0 semantics than the Classic CSV are preserved, meaning interpretation relies on row-shape classification and compact reference grammar of PM4Py.

---

## 8. JSON-OCEL

### 8.1 Classic JSON

Classic JSON uses a dictionary-indexed structure with namespace.

```json
{
  "ocel:global-log": {},
  "ocel:global-event": {},
  "ocel:global-object": {},
  "ocel:objects": {
    "order-1": {
      "ocel:type": "Order",
      "ocel:ovmap": {}
    }
  },
  "ocel:events": {
    "event-1": {
      "ocel:activity": "Create Order",
      "ocel:timestamp": "2026-07-19T00:00:00Z",
      "ocel:vmap": {},
      "ocel:omap": ["order-1"]
    }
  }
}
```

The extended variant recognizes typed E2O relationship, qualifier, O2O, object change.

### 8.2 OCEL 2.0 standard JSON

The explicit OCEL 2.0 path is written as follows:

```json
{
  "objectTypes": [
    {"name": "Order", "attributes": []}
  ],
  "eventTypes": [
    {"name": "Create Order", "attributes": []}
  ],
  "objects": [
    {
      "id": "order-1",
      "type": "Order",
      "attributes": [],
      "relationships": []
    }
  ],
  "events": [
    {
      "id": "event-1",
      "type": "Create Order",
      "time": "2026-07-19T00:00:00Z",
      "attributes": [],
      "relationships": [
        {"objectId": "order-1", "qualifier": "created"}
      ]
    }
  ]
}
```

The object base value and subsequent change are represented by the timestamped attribute repetition of an object. Import separates the first value to `objects`, and the subsequent value to `object_changes`. Export combines that again.

### 8.3 Compression and API distinguish

OCEL 2.0 JSON routes support both `.json.gz` and `.jsonocel.gz`.

`write_ocel_json()` and `write_ocel2_json()` are not the same.

- `write_ocel_json()` uses `OCEL.is_ocel20()` to select `CLASSIC` or the internal `OCEL20` variant.
- `write_ocel2_json()` explicitly selects `OCEL20_STANDARD`.

---

## 9. XML-OCEL

OCEL 2.0 XML exporter uses a hierarchy equivalent in meaning to the standard JSON.

```xml
<log>
  <object-types>...</object-types>
  <event-types>...</event-types>
  <objects>
    <object id="order-1" type="Order">
      <attributes>...</attributes>
      <objects>
        <relationship object-id="order-2" qualifier="parent"/>
      </objects>
    </object>
  </objects>
  <events>
    <event id="event-1" type="Create Order" time="...">
      <attributes>...</attributes>
      <objects>
        <relationship object-id="order-1" qualifier="created"/>
      </objects>
    </event>
  </events>
</log>
```

The exporter extracts the type declaration and uses the base and timestamped object attributes to record the E2O/O2O relationship, including the qualifier. Importer returns it to DataFrame and parsing the typed value, sorting the temporal data and then applying consistency/filtering.

The express OCEL 2.0 XML path supports `.xml.gz` and `.xmlocel.gz`.

---

## 10. SQLite

### 10.1 Classic SQLite

The Classic Pandas variant uses three DataFrames directly.

```text
EVENTS
OBJECTS
RELATIONS
```

This path doesn't use O2O, E2E, object change.

### 10.2 OCEL 2.0 SQLite

The explicit OCEL 2.0 variant uses the following table.

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

`event` and `object` mapping the ID to a logical type. Type-map tables connect logical type names to physical type tables. Each `event_<type>` table stores the timestamp and event attribute, and each `object_<type>` table stores the base value and time change.

`event_object` stores E2O and qualifier, and `object_object` stores O2O and qualifier.

When importing, PM4Py reads the type-specific table and combines the object base row and the change row. Read the Relationship table and add the activity/timestamp/object type to E2O, sort the temporal data and then generate `OCEL`.

---

## 11. Bundled CSV/Parquet

### 11.1 Physical form

Bundles can be directories including `.ocel.zip` archive or `ocel-meta.json`. The default table format is Parquet and you can also choose CSV.

```text
bundle/
├── ocel-meta.json
├── events/
│   ├── event_<encoded-event-type>.parquet
│   └── ...
├── objects/
│   ├── object_<encoded-object-type>.parquet
│   └── ...
├── object_changes/
│   ├── object_changes_<encoded-object-type>.parquet
│   └── ...
└── relations/
    ├── e2o.parquet
    └── o2o.parquet
```

The unsecured characters in the filename from the type name are percent-encoding.

### 11.2 Metadata

`ocel-meta.json` records the following:

```text
OCEL version
bundle format version
CSV 또는 Parquet storage format
event type → event table 및 attribute declaration
object type → object table, changes table 및 attribute declaration
E2O table path
O2O table path
```

### 11.3 Export and import

Export creates metadata describing one event type table, one object type base table and one changes table, a separate E2O/O2O table, path and primitive type. The file is stored in a ZIP archive or directory.

Import reads the metadata and loads all the declared tables. Type-specific frames are concatenated, E2O metadata reconfigured, ID/timestamp normalized, and temporal data sorted to generate `OCEL`.

Bundle supports the most dataset-centric and typed columnar Parquet storage of the examined representations.

---

## 12. Public release API

### 12.1 Classic `write_ocel()`

```python
pm4py.write_ocel(ocel, file_path, objects_path=None)
```

| Expanders | The path of choice. |
| --- | --- |
| `.csv` | Classic extended-table CSV |
| `.jsonocel` | Classic or internal OCEL20 JSON variant |
| `.xmlocel` | Classic XML variant |
| `.sqlite` | Classic Pandas SQLite variant |

### 12.2 express `write_ocel2()`

```python
pm4py.write_ocel2(
    ocel,
    file_path,
    storage_format="parquet",
)
```

| Expanders | The path of choice. |
| --- | --- |
| `.ocel.zip` | Bundled CSV/Parquet |
| `.sqlite` | OCEL 2.0 SQLite |
| `.csv` | Compact OCEL 2.0 CSV |
| `.json`, `.jsonocel` | Standard OCEL 2.0 JSON |
| `.xml`, `.xmlocel` | OCEL 2.0 XML |
| JSON/XML `.gz` is the form | Compressed standard JSON/XML |

### 12.3 Version Conjecture

`OCEL.is_ocel20()` returns true when it finds a non-empty O2O table, a non-empty object-changes table or a non-empty relation qualifier. Generic JSON output selects the variant as a result.

This heuristic does not check `e2e` and is not a full standard version validator.

---

## 13. Normalization and Mutation

Several exporters run the following:

```text
input OCEL
→ ocel_consistency.apply()
→ propagate_relations_filtering()
→ format conversion
→ file write
```

Consistency and filtering can replace or filter the DataFrame held by the transmitted `OCEL`. So the exporter call can change the Status that the caller sees.

The possible changes are as follows:

- Delete row where the required value is invalid
- Convert the identifier and type to string.
- Replace the null qualifier
- The event or object filtering that is not maintained in relation
- O2O, E2E, object-change row filtering with no endpoint.

Not all exporters perform the same sequence. Mutation risk should be evaluated by variant. There is no common result reporting whether any input record has been changed or removed.

---

## 14. Round-Trip conservation matrix

| The format. | E2O | E2O qualifier | O2O | Object change | E2E |
| --- | ---: | ---: | ---: | ---: | ---: |
| Classic extended CSV | Some of them. | There is no stable conservation. | No, you can't. | No, you can't. | No, you can't. |
| Classic SQLite | Yes, I did. | Depending on the Schema column | No, you can't. | No, you can't. | No, you can't. |
| Classic JSON/XML | Yes, I did. | Depending on the variant. | Depending on the extended variant | Depending on the extended variant | No, you can't. |
| Compact OCEL 2.0 CSV | Yes, I did. | Yes, I did. | Yes, I did. | Yes, I did. | No, you can't. |
| Standard OCEL 2.0 JSON | Yes, I did. | Yes, I did. | Yes, I did. | Yes, I did. | No, you can't. |
| OCEL 2.0 XML | Yes, I did. | Yes, I did. | Yes, I did. | Yes, I did. | No, you can't. |
| OCEL 2.0 SQLite | Yes, I did. | Yes, I did. | Yes, I did. | Yes, I did. | No, you can't. |
| OCEL 2.0 bundle | Yes, I did. | Yes, I did. | Yes, I did. | Yes, I did. | No, you can't. |

 — yeon means that he observed an explicit serialization and reconstruction path. It does not prove semantic round-trip equality for all data types or malformed dataset.

Under the OCEL importer/exporter package examined, no code referring to `ocel.e2e` was found.

E2E is a PM4Py in-memory extension, but is not a component of the OCEL 2.0 Specification Definition 2. Therefore, the absence of E2E file round trip is a limitation of PM4Py functionality, but by itself is not the basis for OCEL 2.0.

---

## 15. Major risks and ambiguities

1.  — classic CSV and SQLite do not represent the entire in-memory structure.
2. **Used normalization** — invalid row can be removed without reporting.
3. **Export side mutation** — write operation can change an object that has been delivered.
4.  — without an object table classic CSV reconfigures an object in relation.
5. **API family obscurity** — classic function and the explicit OCEL 2.0 function select different variants.
6. **Active change column** — changed-field name and value must be interpreted together.
7. **Relation denormalization** — Overlapped event/object metadata may be inconsistent with each other.
8.  — has no common contract listing dropped, inferred, coerced, unsupported data.

---

## 16. Preliminary checkpoint for the PIX

### 16.1 A pattern worth looking at

- The format adapter converges to a neutral internal model.
- Classic and OCEL 2.0 variants are explicitly separated.
- Type by type relational and bundle layout
- Separated E2O, O2O, object-change representation
- GZIP and Parquet storage profile

### 16.2 PIX needs to redesign the pattern

- Destructive normalization of import
- Export of mutation
- Structured import/export result not available
- There is no common loss declaration
- E2E file round trip absent
- Silent schema-version reasoning
- Denormalized relation semantics without evidence of discrepancy

### 16.3 Adapter result candidate form

PIX import adapters may need to return more information than `ProcessDataset`.

```text
DatasetImportResult
├── dataset
├── source_format
├── source_format_version
├── normalized_fields
├── rejected_records
├── inferred_records
├── unavailable_components
├── assumptions
└── source references
```

Export adapters may require the following:

```text
DatasetExportResult
├── target_format
├── target_format_version
├── written_components
├── omitted_components
├── lossy_conversions
├── assumptions
└── output artifact reference
```

This is a preliminary design test site and not an approved PIX contract.

---

## 17. Uncertainties

Next, the source test is unknown.

- Exact round-trip equality for all primitive and timestamp types
- Schumpeter scale performance at OCEL volume
- The maximum number of objects and relation that can be processed practically
- Relation denormalization of memory overhead
- The edge-case equivalence of the Python importer and the selective rust importer
- Full compliance with all PM4Py extensions
- The operation of any duplicate or conflicting object attribute instance
- Whether a non-obvious external integration outside the scope of testing serializes E2E

---

## 18. Validity and Withdrawal Conditions

This analysis is valid for the following PM4Py commit.

```text
3329bbcbadce8764f7df660fd88636c30793fbd0
```

In the following cases, the relevant judgments shall be reviewed or withdrawn.

- If PM4Py has changed the public OCEL I/O API
- If the importer/exporter adds the E2E serialization,
- If the exporter is explicitly non-muting
- If the consistency treatment returns structured rejected-record information
- If the Classic CSV or SQLite supports full OCEL 2.0 semantics
- Compact CSV convention or bundle layout changed
- If the round-trip test you run contradicts the source-based conservation matrix,
- If the optional Rust backend actually creates a different structure,
- If PIX changes the canonical data or evidence-lineage requirement

---

## 19. The final evaluation

**PM4Py's `OCEL` is an operation centered container that binds several mutable Pandas DataFrame, including E2O, O2O, E2E, object change, rather than a graph that constitutes an event and object entity as an individual domain object. Format-specific importer and exporter variants merge the external OCEL file into this common object. The explicit OCEL 2.0 JSON, XML, SQLite, compact CSV, bundle path preserves the E2O relationship, qualifier, O2O relationship, object change more fully than the classic CSV and classic SQLite. However, the object creation itself does not guarantee dataset validity, and relation-filter propagation can remove disconnected events and objects allowed by the command. The file-I/O layer also examined does not record E2E relation round-trip or normalization, rejected row, inferred data, mutation, semantic loss in common form. E2E is not a requirement of OCEL 2.0 Definition 2, so it should be separated from the relevant absence and the standard compliance assessment.**
