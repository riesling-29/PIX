# OCPA와 PM4Py의 파일별 OCEL 생성 과정 및 OCEL 2.0 준수 비교

**문서 유형:** Upstream 참조 비교 분석 / OCEL file import 및 OCEL 2.0

**대상 프로젝트:** PIX

**비교 대상:** OCPA 1.3.3, PM4Py 2.7.23.3

**명세 기준:** `OCEL (Object-Centric Event Log) 2.0 Specification`, Version 2.0, 2023-10-16

**분석일:** 2026-07-25

**상태:** Source inspection과 제한된 runtime probe에 기반한 비교 기준선

---

## 0. 목적과 범위

이 문서는 OCPA와 PM4Py가 파일 형식별 외부 representation을 읽어 각각의 in-memory `OCEL`을 만드는 과정을 비교한다.

비교 범위는 다음과 같다.

1. 공개 import API와 extension dispatch
2. CSV, classic JSON/XML/SQLite 처리
3. OCEL 2.0 JSON, XML, SQLite 처리
4. PM4Py의 compact CSV, GZIP 및 CSV/Parquet bundle 확장
5. Identifier, event/object type, attribute, E2O, qualifier, O2O 및 object attribute history 보존
6. Validation, normalization, filtering 및 mutation
7. OCEL 2.0 metamodel 의미 보존과 reference serialization 준수

이 문서는 “파일을 열 수 있다”와 “OCEL 2.0을 준수한다”를 같은 의미로 사용하지 않는다.

```text
Parser acceptance
    파일이 예외 없이 parsing되는가?

Reference syntax conformance
    JSON Schema, XML XSD 또는 relational constraint를 만족하는가?

Metamodel preservation
    Definition 2의 event, object, attribute 및 relation 의미가 보존되는가?

Round-trip conformance
    Import 후 export했을 때 같은 의미를 재구성할 수 있는가?
```

이번 비교는 import와 in-memory object 생성에 초점을 둔다. 모든 primitive type의 export round trip, 대규모 성능 및 malformed-input 전체 동작은 확정하지 않는다.

---

## 1. 비교 기준과 근거

### 1.1 Upstream 기준선

```text
OCPA
Repository: ocpm/ocpa
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3

PM4Py
Repository: process-intelligence-solutions/pm4py
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

OCPA 1.3.3은 package metadata에서 PM4Py 2.2.32에 의존한다. 여기서 비교하는 PM4Py 자체 구현은 2.7.23.3이므로 OCPA 내부 dependency version과 동일하지 않다.

### 1.2 OCEL 2.0 명세 기준선

검사한 명세는 다음 공식 문서의 로컬 사본이다.

- [OCEL 2.0 Specification](https://www.ocel-standard.org/2.0/ocel20_specification.pdf)
- Version 2.0
- 문서 표시일 2023-10-16
- JSON, XML 및 relational SQLite 구현 설명 포함

명세 Definition 2의 핵심 요소는 다음과 같다.

```text
E, O
EA, OA
evtype, time, objtype
eatype, oatype
eaval, oaval
E2O ⊆ Event × Qualifier × Object
O2O ⊆ Object × Qualifier × Object
```

명세는 event가 object와 연결되지 않거나 object가 event와 연결되지 않은 경우도 허용한다. 따라서 “E2O가 없는 record를 제거한다”는 동작은 단순 normalization이 아니라 유효한 OCEL 의미를 줄일 수 있다.

E2E relation은 Definition 2의 구성 요소가 아니다. 따라서 E2E file persistence 부재는 별도의 기능 한계일 수 있지만 OCEL 2.0 미준수 근거로 사용하지 않는다.

### 1.3 명세 내부 XML 불일치

검사한 명세 PDF에는 XML relation element에 관해 서로 충돌하는 artifact가 있다.

```text
Section 7.1 XML example:
    <relationship object-id="..." qualifier="..."/>

Section 7.2 embedded XSD:
    <xs:element name="object"> ...
    relation selector도 .../objects/object 사용
```

명세가 연결한 공식 XSD도 검사 시점에는 `object` element를 사용했다. 반면 PDF의 설명과 예제는 `relationship`을 사용한다.

따라서 이 문서는 XML을 다음 두 층으로 나누어 판정한다.

- Relation의 source, target 및 qualifier 의미를 보존하는지
- 특정 element 이름이 PDF 예제 또는 XSD 중 어느 한쪽과 일치하는지

이 충돌이 해소되기 전에는 XML relation element 이름만으로 완전한 구문 준수 여부를 단정하지 않는다.

### 1.4 Runtime probe의 지위

제한된 runtime probe는 다음 자료를 사용했다.

- PM4Py repository의 `ocel20_example.jsonocel`
- PM4Py repository의 `ocel20_example.xmlocel`
- PM4Py/OCPA repository의 `ocel20_example.sqlite`
- Definition 2가 허용하는 disconnected event/object를 가진 최소 JSON

OCPA의 pinned dependency인 Pandas 1.3.5와 NumPy 1.22.4는 사용한 Python 3.13 환경에 그대로 설치할 수 없었다. 따라서 OCPA runtime 결과는 compatible current dependency를 사용한 보조 근거다. 다만 아래에 기록한 ID-index alignment와 attribute lookup 문제는 runtime 결과만이 아니라 pinned source control flow에서도 확인했다.

---

## 2. 지원 형식과 공개 API

### 2.1 입력 surface 비교

| 입력 family | OCPA 1.3.3 | PM4Py 2.7.23.3 |
| --- | --- | --- |
| CSV event table | 전용 CSV factory | `read_ocel()` classic CSV |
| Classic JSON-OCEL 1.0 | 전용 OCEL factory | `read_ocel()` |
| Classic XML-OCEL 1.0 | DataFrame 반환만 지원 | `read_ocel()` |
| Classic SQLite | 확인된 전용 경로 없음 | `read_ocel()` |
| OCEL 2.0 standard JSON | 지원 경로 없음 | `read_ocel2()` |
| OCEL 2.0 XML | 전용 XML factory | `read_ocel2()` |
| OCEL 2.0 SQLite | 전용 SQLite factory | `read_ocel2()` |
| Compact OCEL 2.0 CSV | 지원 경로 없음 | `read_ocel2()` 확장 |
| JSON/XML GZIP | 지원 경로 없음 | `read_ocel2()` |
| CSV/Parquet bundle | 지원 경로 없음 | `read_ocel2()` 확장 |

PM4Py의 compact CSV와 bundle은 명세 PDF가 상세 정의한 세 reference serialization에는 포함되지 않는다. 그러나 명세 Section 9은 새로운 storage format이 OCEL 2.0 metamodel을 구현하는 것을 허용하고 권장한다. 따라서 이 둘은 “OCEL 2.0 semantic extension format”으로 평가하되 공식 JSON Schema, XML XSD 또는 relational constraint 준수와 혼동하지 않는다.

### 2.2 Dispatch 방식

OCPA에는 모든 형식을 extension으로 자동 선택하는 하나의 facade가 없다.

```text
CSV
    ocpa.objects.log.importer.csv.factory.apply

Classic JSON/XML
    ocpa.objects.log.importer.ocel.factory.apply

OCEL 2.0 SQLite
    ocpa.objects.log.importer.ocel2.sqlite.factory.apply

OCEL 2.0 XML
    ocpa.objects.log.importer.ocel2.xml.factory.apply
```

PM4Py는 classic과 OCEL 2.0 facade를 분리한다.

```text
read_ocel()
    .csv
    .jsonocel
    .xmlocel
    .sqlite

read_ocel2()
    .ocel.zip 또는 bundle directory
    .sqlite
    .csv
    .json / .jsonocel 및 GZIP
    .xml / .xmlocel 및 GZIP
```

`.jsonocel`, `.xmlocel`, `.sqlite`는 호출한 facade에 따라 classic 또는 OCEL 2.0 importer가 달라질 수 있다.

---

## 3. 공통 OCEL 생성 구조

### 3.1 OCPA

OCPA importer는 외부 데이터를 event 중심 DataFrame으로 모은 뒤 여러 representation을 동시에 만든다.

```text
External file
    ↓
Format-specific parsing
    ↓
Event DataFrame
    ├──→ Table
    ├──→ df_to_ocel → ObjectCentricEventLog
    └──→ eog_from_log → EventGraph
                     +
                optional ObjectGraph
                optional ObjectChangeTable
    ↓
OCPA OCEL
```

이 구조에서는 같은 source fact가 여러 표현으로 복제된다.

- Event ID: `Table`과 entity dictionary
- E2O: object-type별 DataFrame column과 `Event.omap`
- E2O qualifier: EventGraph node attribute dictionary
- O2O: `nx.DiGraph`
- Object attribute history: object-type별 change table

Importer가 이 representation들의 동등성을 검증하지 않으므로 생성 성공만으로 일관성이 보장되지 않는다.

### 3.2 PM4Py

PM4Py importer는 외부 데이터를 role별 DataFrame으로 분리한다.

```text
External file
    ↓
Format-specific parsing
    ↓
events / objects / relations / o2o / object_changes
    ↓
ID와 timestamp normalization
    ↓
OCEL(...)
    ↓
ocel_consistency
    ↓
propagate_relations_filtering
    ↓
PM4Py OCEL
```

PM4Py는 E2O와 O2O를 독립 row로 유지하므로 같은 endpoint에 서로 다른 qualifier가 여러 개 있는 경우를 OCPA보다 직접적으로 표현한다.

반면 마지막 consistency/filtering 단계가 source record를 변경하거나 제거할 수 있으며 공통 rejected-record report를 반환하지 않는다.

---

## 4. OCPA의 형식별 처리

### 4.1 CSV

```text
CSV
    ↓ pd.read_csv
object-type cell
    ↓ ast.literal_eval
event ID
    ↓ source ID를 무시하고 0..N-1 string 생성
timestamp
    ↓ Pandas datetime 변환 및 sort
    ↓
Table
    +
df_to_ocel
        ↓ event를 1..N으로 다시 enumerate
        ↓ object-type column에서 Obj 생성
    +
EventGraph
    ↓
OCPA OCEL
```

확인된 의미 범위는 event, activity, timestamp, event attribute 및 object-type별 E2O reference다.

CSV 경로에는 다음 OCEL 2.0 요소가 없다.

- E2O qualifier
- O2O
- dynamic object attribute value

따라서 OCPA CSV는 OCEL 2.0 reference serialization도 아니고 metamodel 전체를 보존하는 형식도 아니다.

### 4.2 Classic JSON-OCEL

```text
Classic JSON dictionary
    ↓ parse_events / parse_objects
ObjectCentricEventLog
    ↓ JSON-to-CSV conversion
Table + EventGraph
    ↓
OCPA OCEL
```

Source event dictionary key는 보존되지 않고 sequential integer ID로 대체된다. 누락된 `start_timestamp`는 event timestamp로 보강된다.

이 parser는 `ocel:events`, `ocel:objects`, `ocel:omap` 등의 classic namespace를 요구한다. Standard OCEL 2.0 JSON의 `events`, `objects`, `eventTypes`, `objectTypes` 구조를 읽지 않는다.

Runtime probe에서 schema-valid standard JSON을 이 factory에 전달했을 때 `KeyError: 'ocel:events'`가 발생했다.

### 4.3 Classic XML-OCEL

Classic XML variant는 event/object DataFrame을 반환할 수 있지만 composite `OCEL` 반환은 명시적으로 거부한다.

```text
return_df=True
    → event DataFrame
    → optional object DataFrame

return_df=False
    → ValueError
```

따라서 classic XML에서 OCPA `OCEL`로 직접 수렴하는 공개 경로로 계산하지 않는다.

### 4.4 OCEL 2.0 SQLite

OCPA SQLite importer가 읽는 table은 명세 relational layout과 대응한다.

```text
event
object
event_map_type
object_map_type
event_<mapped-event-type>
object_<mapped-object-type>
event_object
object_object
```

구성 과정은 다음과 같다.

```text
event + event_<type>
    ↓ merge
event DataFrame

event_object + object
    ↓ event ID × object type별 set aggregation
    ↓ event DataFrame의 object-type column에 update

event DataFrame
    ├──→ Table
    ├──→ df_to_ocel
    └──→ EventGraph

object_object
    ↓ nx.DiGraph

object_<type>
    ↓ ObjectChangeTable
```

Pinned source에는 aggregated E2O의 index가 source event ID이고 destination `event_df`의 index가 기본 RangeIndex인 상태에서 `DataFrame.update()`를 호출하는 경로가 있다. `e1`, `e2`와 같은 일반적인 string event ID에서는 index가 일치하지 않아 object reference가 반영되지 않는다.

제한된 runtime probe에서 relational constraint 24개를 만족한 13-event 예제를 읽었을 때 다음 순서가 재현됐다.

```text
E2O update 결과 entity용 object 0건
    ↓
df_to_ocel의 debug sample helper가 3개 object sampling 시도
    ↓
ValueError: Sample larger than population or is negative
```

OCPA pinned dependency 조합에서의 별도 재실행이 이 결과와 다르면 runtime 판정은 철회해야 한다. 그러나 source index alignment가 수정되지 않는 한 string event ID에 대한 의미 보존 판단은 유지한다.

### 4.5 OCEL 2.0 XML

```text
object-types / event-types
    ↓ attribute type dictionary

objects
    ├──→ object ID → type dictionary
    ├──→ ObjectGraph
    └──→ object-type별 attribute history

events
    ├──→ event DataFrame
    ├──→ object-type별 E2O column
    └──→ event ID → object ID → qualifier dictionary

event DataFrame
    ├──→ Table
    ├──→ df_to_ocel
    └──→ EventGraph
```

확인된 보존과 손실은 다음과 같다.

| 요소 | 관찰 |
| --- | --- |
| Event ID | Table에는 source ID, entity view에는 1-based regenerated ID |
| Event type/time | Table에 저장 |
| Event attribute | lexical value는 저장되지만 선언 type lookup이 실패해 보통 string 처리 |
| E2O endpoint | object-type별 event column에 저장 |
| E2O qualifier | event/object dictionary가 EventGraph node attribute로 이동 |
| O2O | `nx.DiGraph` edge로 저장 |
| Object attribute history | `ObjectChangeTable`에 저장 |
| Object entity | event DataFrame에서 재구성된 object만 entity view에 저장 |

Event attribute parser는 attribute name 앞에 `event_`를 붙인 후 선언 dictionary의 unprefixed key를 조회한다. 표준적인 선언에서는 lookup이 실패하므로 값은 보존되지만 declared primitive type이 적용되지 않고 string fallback이 사용된다.

`df_to_ocel`은 `DataFrame.itertuples()` row를 object type 이름으로 attribute access한다. 공백처럼 Python identifier에 사용할 수 없는 문자가 object type 이름에 있으면 해당 column을 찾지 못할 수 있다.

13-event, 9-object, 20-E2O 예제의 probe에서는 다음이 관찰됐다.

```text
Table:
    13 events
    20 object references
    source event IDs 유지

Entity view:
    13 events
    regenerated event IDs
    6 objects
    공백이 없는 Invoice/Payment object만 남음
```

명세는 object type 이름을 string으로 정의하며 Python identifier로 제한하지 않는다. 따라서 이 누락은 표준 의미 보존과 양립하지 않는다.

### 4.6 Relation multiplicity

Definition 2의 E2O와 O2O는 qualifier를 포함한 triple set이다. 같은 endpoint pair가 서로 다른 qualifier로 여러 번 존재할 수 있으며 relational section도 이를 명시한다.

OCPA는 다음 구조를 사용한다.

```text
E2O qualifier:
    qualifier_dict[event_id][object_id] = qualifier

O2O:
    nx.DiGraph.add_edge(source, target, qualifier=...)
```

두 구조 모두 같은 endpoint pair의 복수 qualifier를 독립 relation으로 유지하지 못하고 나중 값으로 덮어쓸 수 있다.

---

## 5. PM4Py의 형식별 처리

### 5.1 Classic CSV

Classic CSV importer는 extended event table과 선택적 objects table을 읽는다.

```text
event CSV
    ↓ object-type column의 list parsing
events + E2O relations

optional object CSV
    ↓ objects

object file 없음
    ↓ E2O reference에서 object 추론

    ↓ OCEL → consistency/filtering
```

Qualifier, O2O 및 object attribute history를 안정적으로 표현하지 않으므로 OCEL 2.0 전체 보존 형식이 아니다.

### 5.2 Classic JSON/XML/SQLite

`read_ocel()`의 classic family는 OCEL 1.0 또는 PM4Py classic representation을 공통 DataFrame container로 옮긴다.

```text
Classic source
    ↓ format parser
events / objects / relations
    ↓ OCEL
```

Variant에 따라 extended O2O와 change를 인식하는 경로가 있어도 명시적 `read_ocel2()` reference-profile import와 동일한 contract로 보지 않는다.

### 5.3 Compact OCEL 2.0 CSV

PM4Py compact CSV는 row shape와 `ot:<object-type>` cell grammar로 entity 종류를 구분한다.

```text
event row
    ID + activity + timestamp

object declaration row
    ID/activity/timestamp 없음

object change row
    timestamp만 존재

O2O row
    special activity marker
```

Importer는 reference string에서 object ID, qualifier 및 JSON-encoded object attribute를 분해하고 다음 DataFrame을 만든다.

```text
events
objects
relations
o2o
object_changes
```

이 형식은 OCEL 2.0 metamodel 요소를 폭넓게 담지만 PDF의 JSON Schema, XML XSD 또는 relational constraint로 검증할 수 없는 PM4Py-specific serialization이다.

### 5.4 Standard OCEL 2.0 JSON

```text
objectTypes / eventTypes
    ↓ attribute type dictionary

events
    ↓ activity, timestamp, attributes
    ↓ typed E2O relationship

objects
    ↓ base attributes
    ↓ later values → object_changes
    ↓ relationships → O2O

temporary classic-shaped dictionary
    ↓ classic.get_base_ocel
    ↓ OCEL
    ↓ consistency/filtering
```

확인된 장점은 다음과 같다.

- Standard top-level array를 직접 인식
- E2O qualifier를 독립 relation row로 유지
- O2O qualifier를 독립 row로 유지
- Object attribute value history를 base와 change로 분리
- GZIP input 지원

제한은 다음과 같다.

- `read_ocel2_json()` 자체는 JSON Schema validation을 실행하지 않는다.
- Object attribute의 같은-name entry는 파일 배열의 첫 항목을 base로 선택하며 timestamp 순서 정렬을 먼저 하지 않는다.
- Type conversion 실패 시 일부 값은 원래 representation으로 남을 수 있다.
- 최종 relation-filter propagation이 disconnected event/object를 제거한다.

### 5.5 OCEL 2.0 XML

```text
object-types / event-types
    ↓ declared type map

objects
    ↓ objects, O2O, attribute history

events
    ↓ events, E2O, event attributes

DataFrame 생성 및 temporal sort
    ↓ OCEL
    ↓ consistency/filtering
```

Parser는 relationship container의 child tag 이름 자체를 검사하지 않고 `object-id`와 `qualifier` attribute를 읽는다. 따라서 PDF 예제의 `relationship`과 embedded XSD의 `object` 형태를 모두 parsing할 수 있지만, 이는 strict XSD validation을 수행한다는 뜻은 아니다.

`read_ocel2_xml()`은 XSD validation을 자동 실행하지 않는다. 별도 `validation.xmlocel.apply()` helper가 있지만 caller가 schema path와 함께 명시적으로 호출해야 한다.

### 5.6 OCEL 2.0 SQLite

PM4Py는 type map과 type-specific table을 이용해 role별 DataFrame을 만든다.

```text
event + event_map_type + event_<type>
    ↓ events

object + object_map_type + object_<type>
    ↓ base objects + object_changes

event_object
    ↓ relations + denormalized event/object metadata

object_object
    ↓ o2o

    ↓ temporal sort
    ↓ OCEL
    ↓ consistency/filtering
```

Direct importer에는 relational validation option이 있으나 기본값은 `False`다.

```text
validation=False
except_if_invalid=False
```

공개 `read_ocel2_sqlite()` facade는 검사한 source에서 encoding만 전달하므로 이 option을 직접 노출하지 않는다. Validation을 요구하는 caller는 lower-level importer 또는 validation helper를 별도로 사용해야 한다.

### 5.7 Bundle과 GZIP

GZIP JSON/XML은 compression wrapper 뒤 standard importer로 들어가므로 압축 여부가 in-memory model을 바꾸지 않는다.

Bundle은 metadata에서 table path와 primitive type을 읽고 event/object type별 CSV 또는 Parquet table, E2O, O2O 및 object-change table을 concatenate한다.

```text
ocel-meta.json
events/event_<type>.*
objects/object_<type>.*
object_changes/object_changes_<type>.*
relations/e2o.*
relations/o2o.*
```

Bundle은 공식 reference serialization이 아니라 metamodel-oriented extension이다. 명세의 semantic 요소를 저장할 수 있는지는 source에서 확인되지만 모든 bundle variant의 cross-tool interoperability는 알 수 없음이다.

---

## 6. 동일 OCEL 2.0 예제의 생성 결과

### 6.1 Reference example

JSON Schema를 만족한 standard JSON 예제와 대응 XML/SQLite 예제의 논리적 크기는 다음과 같다.

```text
events:          13
objects:          9
E2O:             20
O2O:              7
object changes:   3
```

### 6.2 PM4Py

PM4Py 2.7.23.3은 JSON, XML 및 SQLite를 각각 읽어 모두 다음 크기의 `OCEL`을 만들었다.

| 형식 | Event | Object | E2O | Qualified E2O | O2O | Object change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard JSON | 13 | 9 | 20 | 20 | 7 | 3 |
| XML | 13 | 9 | 20 | 20 | 7 | 3 |
| SQLite | 13 | 9 | 20 | 20 | 7 | 3 |

이 결과는 해당 예제에서 세 importer가 공통 object model로 수렴한다는 근거다. 모든 합법적 OCEL 2.0 instance에 대한 동등성을 입증하지는 않는다.

### 6.3 OCPA

| 형식 | 결과 |
| --- | --- |
| Standard JSON | 지원 경로 없음, classic factory에서 key error |
| XML | Table은 13 events와 20 references를 만들었으나 entity view는 6/9 objects만 보존 |
| SQLite | relational validation을 통과한 예제에서 importer exception 재현 |

OCPA XML의 `Table`, entity dictionary, EventGraph, ObjectGraph 및 ObjectChangeTable이 서로 다른 identity와 completeness를 가질 수 있으므로 어느 하나만 보고 전체 import가 보존됐다고 판단할 수 없다.

---

## 7. OCEL 2.0 요구사항별 비교

표의 판정 용어는 다음 의미다.

```text
지원
    명시적 representation과 import 경로가 확인됨

부분
    일부 representation에는 존재하지만 loss 또는 drift 경로가 확인됨

미지원
    명시적 import 경로가 없음

유보
    명세 artifact 충돌 또는 runtime evidence 부족으로 확정 불가
```

| 요구사항 | OCPA 1.3.3 | PM4Py 2.7.23.3 |
| --- | --- | --- |
| Standard JSON import | 미지원 | 지원 |
| XML import | 부분 | 지원 |
| Relational SQLite import | 부분: source 경로는 있으나 valid sample failure 재현 | 지원 |
| Event ID 보존 | 부분: representation별 재생성 | 지원: string normalization 발생 |
| Event type와 timestamp | 지원 | 지원 |
| Typed event attribute | 부분: XML declared type lookup 불일치 | 지원, conversion failure는 strict rejection 아님 |
| Object와 object type | 부분: event-derived entity view에서 누락 가능 | 지원 |
| Dynamic object attribute | 부분: change table에 보존, representation 분산 | 지원 |
| Qualified E2O | 부분: endpoint pair별 qualifier collapse 가능 | 지원 |
| Qualified O2O | 부분: `DiGraph`가 multi-qualifier collapse 가능 | 지원 |
| Unconnected event/object | 안정적 보존 근거 없음 | 미보존: relation filtering으로 삭제 재현 |
| Schema validation 자동 실행 | 없음 | 없음 |
| 별도 validation utility | 확인되지 않음 | JSON/XML/relational helper 있음 |
| Structured rejected/loss report | 없음 | 없음 |

### 7.1 Strict conformance를 인정할 수 없는 근거

OCPA에 대해서는 다음 반증이 존재한다.

- Standard JSON importer 부재
- Valid relational sample의 importer failure
- XML object type 이름에 따른 entity 누락
- Representation별 event ID drift
- 같은 endpoint의 복수 qualifier collapse
- Automatic schema validation 부재

PM4Py에 대해서는 다음 반증이 존재한다.

- Definition 2가 허용한 disconnected event/object 삭제
- JSON/XML import에서 schema validation을 자동 수행하지 않음
- Invalid row가 structured report 없이 제거될 수 있음
- JSON/XML object attribute history가 source order에 의존할 수 있음

따라서 어느 library도 검사한 범위에서 “모든 유효 OCEL 2.0을 손실 없이 수용하는 strict conforming importer”라고 단정할 수 없다.

### 7.2 상대적 의미 보존

확인된 standard example과 source representation만 비교하면 PM4Py가 OCPA보다 다음 영역에서 강한 근거를 가진다.

- 세 reference serialization 모두에 대한 명시적 import path
- Event/object/relation의 독립 table
- 같은 endpoint pair의 복수 qualifier 표현
- JSON/XML/SQLite example의 동일 component count
- 별도 validation helper

이 상대 평가는 PM4Py가 완전 준수한다는 뜻이 아니다. Disconnected record 삭제는 Definition 2와 직접 충돌하는 확인된 반례다.

---

## 8. XML 구문 판정의 유보 범위

명세 PDF의 XML example, embedded XSD 및 연결된 XSD가 relation child 이름에 관해 일치하지 않는다.

이 때문에 다음은 현재 확정하지 않는다.

- `<relationship>`만 표준인지
- `<object>`만 표준인지
- 둘 다 호환 형태로 허용해야 하는지

확인된 사실은 다음과 같다.

- OCPA와 PM4Py parser는 child tag 이름을 검사하지 않아 양쪽 형태를 읽을 수 있다.
- Parser acceptance는 XSD validation과 동일하지 않다.
- PM4Py repository의 `relationship` 예제는 검사한 XSD에서 invalid로 판정됐다.
- OCPA repository의 `object` 예제도 `time="0"`과 relation entry의 required `type` 문제로 검사한 XSD에서 invalid로 판정됐다.

공식 명세 또는 schema errata가 element model을 하나로 정리하면 이 유보를 해제해야 한다.

---

## 9. PIX에 대한 시사점

### 9.1 Import adapter의 최소 단계

두 library의 손실 경로를 피하려면 PIX importer는 parsing과 canonicalization을 분리할 필요가 있다.

```text
SourceArtifact
    ↓
SyntaxValidationResult
    ↓
ParsedOCELRecords
    ↓
SemanticValidationResult
    ↓
Canonical ProcessDataset
    ↓
Derived EventGraph / ProcessExecution / Variant
```

### 9.2 필요한 evidence

```text
DatasetImportResult
├── source_format
├── source_format_version
├── syntax_profile
├── syntax_validation
├── semantic_validation
├── dataset
├── identifier_mapping
├── normalized_fields
├── rejected_records
├── inferred_records
├── omitted_components
├── lossy_conversions
├── assumptions
└── source_references
```

### 9.3 권장 보존 규칙

- Event와 object는 E2O 존재 여부와 무관하게 보존한다.
- E2O와 O2O는 endpoint pair가 아니라 `(source, qualifier, target)` identity를 유지한다.
- Source ID와 normalized ID를 별도 mapping으로 남긴다.
- Object attribute value는 source order가 아니라 timestamp와 source position을 함께 기록한다.
- Schema-valid와 semantic-valid를 구분한다.
- Import 중 row를 제거하거나 type을 coercion하면 결과에 기록한다.
- EventGraph는 canonical relation에서 파생하고 source dataset과 섞지 않는다.

이는 현재 비교에서 도출한 설계 후보이며 승인된 PIX architecture 결정은 아니다.

---

## 10. 미확인 사항

다음은 현재 근거만으로 알 수 없음이다.

- OCPA pinned dependency 전체를 재현한 환경에서 SQLite importer가 같은 exception을 내는지
- PM4Py Python importer와 optional Rust importer의 모든 edge-case 동등성
- JSON/XML의 모든 primitive type과 timezone round-trip equality
- 같은 object attribute가 동일 timestamp에 여러 번 존재할 때 두 library의 최종 의미
- Malformed relation과 dangling endpoint의 모든 variant별 동작
- Compact CSV와 bundle의 third-party interoperability
- 대규모 OCEL에서 format별 memory와 처리량
- XML example/XSD 충돌에 대한 공식 errata의 최종 해석

검증되지 않은 성공률, 손실 빈도 및 성능 수치는 알 수 없음이다.

---

## 11. 유효기간과 철회 조건

이 비교는 다음 upstream commit과 명세 문서에 유효하다.

```text
OCPA:   de056e0203a3fa4a9bbc19a95e001eada323074a
PM4Py: 3329bbcbadce8764f7df660fd88636c30793fbd0
OCEL:  Specification Version 2.0, document date 2023-10-16
```

다음 경우 관련 판단을 재검토하거나 철회한다.

- OCPA가 standard JSON importer를 추가한 경우
- OCPA가 SQLite E2O index alignment를 수정한 경우
- OCPA가 source ID invariant와 representation consistency validation을 도입한 경우
- OCPA가 E2O/O2O를 multi-relation structure로 변경한 경우
- PM4Py가 disconnected event/object를 보존하도록 filtering contract를 변경한 경우
- PM4Py가 import 시 schema 및 semantic validation을 기본으로 수행한 경우
- 어느 library든 structured rejected/loss report를 도입한 경우
- Optional Rust backend가 Python backend와 다른 의미 보존 결과를 보이는 경우
- OCEL 2.0 XML example과 XSD 충돌에 대한 공식 errata가 발표된 경우
- Pinned dependency runtime test가 source-level 판단을 반증한 경우
- PIX가 evidence-lineage 또는 canonical dataset 요구를 변경한 경우

---

## 12. 최종 평가

**OCPA 1.3.3은 CSV와 classic JSON을 분석용 복합 `OCEL`로 만들고 OCEL 2.0 XML·SQLite의 O2O, qualifier 및 object change를 일부 representation에 수용하지만, standard JSON 부재, valid SQLite example의 실패 경로, XML의 object 누락과 typed attribute 손실, representation별 ID drift 및 multi-qualifier collapse 때문에 OCEL 2.0 strict importer로 판단할 근거가 없다. PM4Py 2.7.23.3은 standard JSON·XML·SQLite와 추가 compact/bundle format을 공통 relational `OCEL`로 수렴시키며 검사한 연결형 예제에서는 세 reference format의 component count를 동일하게 보존했으므로 상대적으로 명세 적합성이 높다. 그러나 명세가 허용한 disconnected event/object를 relation filtering에서 삭제하는 반례와 기본 schema validation·loss report 부재가 확인되므로 PM4Py 역시 완전 준수로 단정할 수 없다. PIX는 PM4Py의 explicit relation model을 출발점으로 삼되, schema validation과 semantic validation을 분리하고 disconnected record, source identity, multi-qualifier relation 및 모든 normalization/loss evidence를 canonical import contract에 명시해야 한다.**
