# OCEL 2.0 표준, OCPA 및 PM4Py의 OCEL 객체 모델 비교

- **문서 유형:** Upstream 참조 비교 분석 / OCEL 메타모델 및 in-memory 객체
- **대상 프로젝트:** PIX
- **비교 대상:** OCEL 2.0, OCPA 1.3.3, PM4Py 2.7.23.3
- **초기 분석일:** 2026-07-24
- **재정리일:** 2026-07-26
- **상태:** 공식 명세, upstream source 및 제한된 기존 runtime evidence에 기반한 비교 기준선

---

## 0. 목적과 범위

이 문서는 다음 세 대상을 같은 의미 축에서 비교한다.

```text
OCEL 2.0
    규범적 메타모델과 reference serialization

PM4Py OCEL
    표준 데이터를 수용하는 관계형 DataFrame 중심 Python 객체

OCPA OCEL
    객체 중심 분석과 process execution을 지원하는 복합 Python 객체
```

OCEL 2.0은 Python class가 아니다. 따라서 이 비교는 세 구현체의 우열 비교가
아니라 다음 질문에 답하기 위한 것이다.

1. 표준이 보존하도록 요구하는 의미는 무엇인가?
2. PM4Py와 OCPA는 그 의미를 어떤 in-memory representation으로 바꾸는가?
3. 각 representation에서 어떤 정보가 명시적이고 어떤 정보가 파생되는가?
4. qualifier, object change, disconnected record 및 source identity가 보존되는가?
5. PIX는 무엇을 canonical contract로 채택하고 무엇을 derived computation으로
   분리해야 하는가?

파일별 parser와 strict import conformance의 상세 경로는 다음 문서가 소유한다.

```text
1_OCPA_PM4PY_OCEL_FILE_IMPORT_AND_OCEL20_COMPLIANCE_COMPARISON.md
```

이 문서는 위 파일 import 비교를 객체 모델 관점에서 요약하지만 모든 parser
분기를 다시 서술하지 않는다.

---

## 1. 비교 기준과 증거

### 1.1 OCEL 2.0

```text
Document: OCEL (Object-Centric Event Log) 2.0 Specification
Version:  2.0
Date:     2023-10-16
URL:      https://www.ocel-standard.org/2.0/ocel20_specification.pdf
```

공식 명세는 JSON, XML 및 relational SQLite reference serialization을 설명한다.

### 1.2 OCPA

```text
Repository: https://github.com/ocpm/ocpa.git
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3
```

### 1.3 PM4Py

```text
Repository: https://github.com/process-intelligence-solutions/pm4py.git
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

### 1.4 비교 시 주의점

OCPA 1.3.3의 package metadata는 `pm4py==2.2.32`에 의존한다. 이 문서는 OCPA
1.3.3 자체 객체 모델과 PM4Py 2.7.23.3 자체 객체 모델을 비교하며, OCPA가
내부적으로 사용하는 PM4Py 2.2.32와 2.7.23.3의 runtime 동등성을 주장하지 않는다.

증거 수준은 다음처럼 구분한다.

```text
확인된 사실
    공식 명세 또는 지정 commit의 source에서 직접 확인

관찰된 동작
    기존 comparison/1에 기록된 제한된 runtime probe

해석
    확인된 구조가 갖는 책임과 위험에 대한 설명

가설
    PIX 구현과 반례 fixture로 아직 검증하지 않은 설계 예상

미확정
    현재 증거로 판단할 수 없음
```

---

## 2. OCEL 2.0 규범 모델

명세 Definition 2의 핵심 구조는 다음과 같다.

```text
L = (
    E, O,
    EA, OA,
    evtype, time, objtype,
    eatype, oatype,
    eaval, oaval,
    E2O, O2O
)
```

각 요소의 의미는 다음과 같다.

```text
E
    Event identity 집합

O
    Object identity 집합

EA / OA
    Event attribute와 object attribute 이름

evtype / objtype
    Event type과 object type

eatype / oatype
    Attribute value type

eaval
    Event attribute value

oaval
    Timestamp가 포함된 object attribute value history

E2O ⊆ Event × Qualifier × Object
    Qualified event-to-object relation

O2O ⊆ Object × Qualifier × Object
    Qualified object-to-object relation
```

### 2.1 Relation identity

표준 relation의 identity는 endpoint pair만이 아니다.

```text
(e1, "item", o1)
(e1, "target", o1)
```

두 relation은 source와 target이 같아도 qualifier가 다르므로 서로 다른
relation이다. O2O도 같은 원칙을 적용한다.

### 2.2 Dynamic object attribute

Object attribute는 하나의 현재 값만 갖는 것이 아니라 timestamp에 따른 값
history를 가질 수 있다. 따라서 마지막 값만 남기는 representation은 표준 의미를
축소할 수 있다.

### 2.3 Disconnected record

Definition 2는 모든 event 또는 object가 반드시 E2O에 참여해야 한다는 totality
constraint를 명시하지 않는다. 따라서 E2O가 없다는 이유만으로 record를 제거할
표준 근거는 확인되지 않았다.

### 2.4 E2E

E2E relation은 Definition 2의 구성 요소가 아니다. 구현체가 E2E를 제공할 수는
있지만 이는 OCEL 2.0 core metamodel의 확장으로 구분해야 한다.

---

## 3. PM4Py의 OCEL 객체

PM4Py의 `pm4py.objects.ocel.obj.OCEL`은 역할별 Pandas DataFrame과 metadata를
묶는 mutable container다.

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

### 3.1 역할별 표현

```text
events
    Event ID, activity, timestamp, event attribute

objects
    Object ID, object type, object attribute

relations
    Event ID, object ID, qualifier 및 denormalized metadata

o2o
    Source object, target object, qualifier

e2e
    Source event, target event, qualifier

object_changes
    Object ID, timestamp, changed field 및 변경 값
```

E2O와 O2O가 독립 row이므로 같은 endpoint pair에 여러 qualifier가 존재하는
경우를 직접 표현할 수 있다.

### 3.2 중심 관점

확인된 field와 importer 경로를 바탕으로 하면 PM4Py는 OCEL을 다음 관점으로
다룬다고 해석할 수 있다.

> Event, object 및 relation record를 보관하고 format adapter와 algorithm에
> 공급하는 관계형 dataset container.

Graph, object projection 및 process execution은 core `OCEL` field가 아니라
필요한 algorithm이 table에서 도출하는 결과다.

### 3.3 Consistency와 mutation

확인된 경로에는 다음 동작이 있다.

- Identifier의 string normalization;
- timestamp parsing과 temporal sort;
- invalid 또는 empty 필수 field row 제거 가능;
- 누락 qualifier 대체;
- relation filtering의 event, object, O2O, E2E 및 object change 전파;
- export 전 consistency/filtering에 의한 caller object 변경 가능.

이 동작이 존재해도 어떤 source record가 제거·대체·coercion됐는지 structured
result로 반환하지 않는다. 따라서 PM4Py 객체를 evidence-preserving canonical
dataset으로 바로 사용할 근거는 부족하다.

---

## 4. OCPA의 OCEL 객체

OCPA의 `ocpa.objects.log.ocel.OCEL`은 하나의 논리적 log를 여러 분석용
representation으로 materialize하는 mutable composite다.

```text
OCPA OCEL
├── log: Table
├── obj: ObjectCentricEventLog
├── graph: EventGraph
├── parameters: dict
├── o2o_graph: ObjectGraph | None
└── change_table: ObjectChangeTable | None
```

### 4.1 Representation별 역할

```text
Table
    Event 중심 DataFrame
    Object type별 column에 관련 object ID collection 저장

ObjectCentricEventLog
    Event와 Obj entity dictionary
    Event.omap과 object-event mapping
    Object별 sequence와 trace

EventGraph
    같은 object를 공유하는 timestamp-ordered event graph
    일부 importer에서 E2O qualifier dictionary도 보유

ObjectGraph
    O2O edge와 qualifier

ObjectChangeTable
    Object type별 attribute-change table
```

`process_executions`와 `variants`는 `OCEL` property 접근 시 계산되고 cache된다.
Variant 계산은 `Table`에 derived column을 추가할 수 있다.

### 4.2 중심 관점

확인된 field와 lazy calculation을 바탕으로 하면 OCPA는 OCEL을 다음 관점으로
다룬다고 해석할 수 있다.

> Object를 통해 연결된 event 흐름을 즉시 분석할 수 있도록 원본과 파생 view를
> 결합한 분석 작업공간.

### 4.3 Identity와 consistency

확인된 importer path에는 다음 동작이 있다.

- 일부 CSV/classic JSON path의 sequential event ID 생성;
- `Table`, `EventGraph`, entity view 사이의 ID-space 차이 가능;
- E2O fact의 object-type column, `Event.omap` 및 graph metadata 중복;
- constructor에서 representation 간 invariant를 강제하지 않음;
- lazy calculation에 의한 cache와 Table 변경.

OCPA `OCEL` instance가 생성됐다는 사실만으로 모든 representation이 같은 source
identity와 completeness를 공유한다고 볼 수 없다.

---

## 5. 표준 요소별 3자 비교

| 비교 항목 | OCEL 2.0 표준 | PM4Py 2.7.23.3 | OCPA 1.3.3 |
| --- | --- | --- | --- |
| 성격 | 규범적 의미 모델 | 관계형 DataFrame container | 분석용 composite workspace |
| Event | ID, type, time, typed attributes | `events` row | `Table` row와 `Event` entity |
| Object | ID, type, time-indexed attributes | `objects` row | `Obj` entity와 type별 reference |
| Type schema | Event/object type과 attribute type 명시 | DataFrame column/dtype 및 importer metadata로 변환 | metadata, Table 및 entity 모델에 분산 |
| E2O | `(event, qualifier, object)` | 독립 `relations` row | `omap`, type별 column, qualifier dictionary |
| O2O | `(source, qualifier, target)` | 독립 `o2o` row | `ObjectGraph`의 `DiGraph` edge |
| Dynamic object attribute | Timestamp별 history | `object_changes` | `ObjectChangeTable` |
| 같은 endpoint의 복수 qualifier | 서로 다른 relation | 독립 row로 표현 가능 | dictionary/`DiGraph`에서 collapse 가능 |
| E2E | Core 요소 아님 | 별도 확장 table | Core field 확인되지 않음 |
| Graph | 표준 canonical component 아님 | algorithm이 필요할 때 파생 | top-level `OCEL`의 필수/선택 component |
| Process execution | 표준이 정의하지 않음 | 별도 projection/algorithm | lazy property와 cache |
| Disconnected record | invalid로 판정할 근거 없음 | filtering으로 삭제되는 반례 | 안정적 보존 근거 없음 |
| 자동 schema validation | 공식 schema 제공 | importer 기본 실행 아님 | 기본 실행 근거 없음 |
| Structured loss report | 구현 책임 | 없음 | 없음 |
| Mutability | 구현체에 위임 | mutable table/container | mutable composite/cache |

---

## 6. OCEL 2.0 reference format과 수용 범위

### 6.1 표준

공식 reference serialization은 다음 세 가지다.

```text
JSON
XML
Relational SQLite
```

### 6.2 PM4Py

PM4Py에는 다음 명시적 경로가 확인됐다.

- Standard OCEL 2.0 JSON;
- OCEL 2.0 XML;
- OCEL 2.0 SQLite;
- compact CSV, bundle 및 GZIP extension.

Compact CSV와 bundle은 OCEL 2.0 의미 요소를 담을 수 있지만 공식 reference
serialization과 같은 의미로 취급해서는 안 된다.

### 6.3 OCPA

OCPA에는 다음 범위가 확인됐다.

- Standard JSON 전용 importer 없음;
- OCEL 2.0 XML importer 존재;
- OCEL 2.0 SQLite importer 존재;
- O2O, qualifier 및 object change를 일부 representation에 수용.

지원 경로 존재만으로 모든 표준 의미가 모든 internal representation에 손실 없이
전달된다고 볼 수 없다.

---

## 7. 제한된 reference example 관찰

기존 `comparison/1`에 기록된 schema-valid standard example의 논리적 크기는
다음과 같다.

```text
Events:          13
Objects:          9
E2O:             20
O2O:              7
Object changes:   3
```

### 7.1 PM4Py

| 형식 | Event | Object | E2O | Qualified E2O | O2O | Object change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Standard JSON | 13 | 9 | 20 | 20 | 7 | 3 |
| XML | 13 | 9 | 20 | 20 | 7 | 3 |
| SQLite | 13 | 9 | 20 | 20 | 7 | 3 |

검사된 연결형 예제에서는 세 importer가 공통 PM4Py `OCEL` component count로
수렴했다. 이는 모든 유효 OCEL 2.0 instance의 손실 없는 수용을 입증하지 않는다.

### 7.2 OCPA

| 형식 | 관찰 결과 |
| --- | --- |
| Standard JSON | 지원 경로 없음, classic factory에서 key error |
| XML | Table은 13 events와 20 references, entity view는 6/9 objects |
| SQLite | relational validation을 통과한 예제에서 importer exception |

이 결과는 기존 문서의 제한된 runtime probe다. 이번 재정리 작업에서는 probe를
다시 실행하지 않았다.

---

## 8. Strict conformance를 단정할 수 없는 이유

### 8.1 PM4Py 반증

- Definition 2에서 invalid로 판정할 근거가 없는 disconnected event/object 삭제;
- JSON/XML import 시 schema validation을 기본 수행하지 않음;
- invalid 또는 filtered row의 structured loss report 부재;
- object attribute history 처리의 source-order 의존 가능성.

### 8.2 OCPA 반증

- Standard JSON importer 부재;
- valid relational sample의 importer failure;
- representation별 event identity drift 가능;
- XML entity view의 object 누락 경로;
- E2O/O2O의 동일 endpoint 복수 qualifier collapse 가능;
- automatic schema validation과 structured loss report 부재.

### 8.3 상대 평가의 범위

검사된 source와 example에서는 PM4Py가 다음 항목에서 상대적으로 강한 근거를
가진다.

- 세 reference serialization의 명시적 import path;
- Event/object/relation의 독립 table;
- qualifier multiplicity의 독립 row 표현;
- 형식별 동일 component count;
- 별도 validation helper.

이 상대 평가는 PM4Py의 완전 준수를 의미하지 않는다. 어느 library도 현재
증거만으로 모든 유효 OCEL 2.0을 손실 없이 수용하는 strict conforming importer로
판정할 수 없다.

---

## 9. 계산 구조에 대한 의미

### 9.1 PM4Py

PM4Py 객체 구조는 다음 작업에 유리하다.

- format adapter의 공통 중간 representation;
- relation 종류별 filtering;
- object-type projection과 flattening;
- 필요에 따른 graph/model 생성.

Core `OCEL`만으로 process execution 의미가 결정되지는 않는다. 선택한 object
type, projection operator 및 algorithm parameter가 별도로 필요하다.

### 9.2 OCPA

OCPA 객체 구조는 다음 작업에 유리하다.

- object-sharing EventGraph traversal;
- connected-component process execution;
- leading-object process execution;
- graph 기반 variant와 object-centric analysis.

그 대가는 canonical input, graph, process-execution cache 및 variant state가 하나의
mutable `OCEL` 객체에 섞일 수 있다는 점이다.

### 9.3 반론

OCPA의 복합 representation은 분석 응답성을 위한 의도된 최적화일 수 있으며,
복합 구조 자체가 오류를 의미하지 않는다. PM4Py의 DataFrame 분리도 relation
denormalization과 mutation 위험을 자동으로 해결하지 않는다.

따라서 PIX의 구조 결정은 library 형태의 단순 복제가 아니라 source identity,
determinism 및 evidence lineage 요구를 기준으로 해야 한다.

---

## 10. PIX 채택 판단

### 10.1 OCEL 2.0

```text
Role:
    NORMATIVE SEMANTIC BASELINE

Decision:
    CONCEPTUAL REUSE
```

채택 후보:

- Event와 object의 독립 identity;
- 명시적인 event/object type;
- typed attribute;
- timestamp가 포함된 object attribute history;
- qualified E2O와 O2O;
- relation multiplicity.

### 10.2 PM4Py

```text
Decision:
    REFERENCE ONLY

Selected design elements:
    CONCEPTUAL REUSE
```

참조할 요소:

- Event, object, E2O, O2O 및 object change의 물리적 분리;
- format adapter가 공통 dataset model로 수렴하는 구조;
- relation을 독립 row로 유지하는 방식.

채택하지 않을 요소:

- PM4Py object 또는 runtime dependency;
- pandas-first public contract;
- destructive normalization과 silent filtering;
- broad discovery/visualization/model ecosystem.

### 10.3 OCPA

```text
Decision:
    REFERENCE ONLY

Selected design elements:
    CONCEPTUAL REUSE
```

참조할 요소:

- Object-sharing EventGraph 의미론;
- connected-component와 leading-object process execution;
- object-centric variant 및 graph 활용 방식.

채택하지 않을 요소:

- OCPA object 또는 runtime dependency;
- canonical input과 derived cache를 결합한 mutable workspace;
- qualifier를 endpoint dictionary/`DiGraph`로 축약하는 representation;
- factory/variant framework의 자동 도입.

### 10.4 PIX 독립 구현

```text
Decision:
    INDEPENDENT REIMPLEMENTATION
```

가능한 canonical dataset 경계:

```text
ProcessDataset
├── event_types
├── object_types
├── events
├── objects
├── event_attribute_values
├── object_attribute_values
├── event_object_relations
└── object_object_relations
```

필수 보존 규칙 후보:

- Event/object를 E2O 존재 여부와 무관하게 보존;
- E2O/O2O identity를 `(source, qualifier, target)`으로 유지;
- source ID와 normalized ID를 별도 mapping으로 기록;
- object attribute history에 timestamp와 source position 기록;
- schema-valid와 semantic-valid를 구분;
- 삭제, coercion, inference 및 unavailable component를 result에 기록;
- EventGraph와 process execution을 canonical dataset에서 파생한 versioned
  computation으로 취급;
- E2E가 필요하면 OCEL 2.0 core와 분리한 명시적 extension으로 취급.

### 10.5 Algorithm 결정

```text
Decision:
    DEFER
```

Object projection, trace reconstruction, process execution 및 graph algorithm은
각각의 입력 계약, 결정성, 반례 fixture 및 evidence behavior를 검증한 뒤 채택 또는
독립 구현을 결정한다. 이 문서는 알고리즘 채택을 승인하지 않는다.

### 10.6 검증 전 가설

다음은 현재 구조 비교에서 도출한 가설이다.

> OCEL 2.0 의미에 정렬된 canonical dataset을 immutable source로 유지하고 graph,
> process execution 및 variant를 versioned derived computation으로 분리하면,
> OCPA식 복수 representation을 한 객체에 함께 유지하는 방식보다 source identity와
> loss evidence를 더 명확하게 보존할 수 있다.

이 가설은 PIX 구현과 대표 fixture로 검증되지 않았다. 직접 library object를
사용하는 방식이 동일한 determinism과 evidence lineage를 더 낮은 복잡도로
제공하거나, canonical/derived 분리가 실제 vertical slice를 불필요하게 방해한다는
근거가 나오면 철회한다.

---

## 11. 미확인 사항

현재 근거만으로 다음은 알 수 없음이다.

- OCPA pinned dependency 전체를 재현한 환경에서의 모든 importer 결과;
- PM4Py Python importer와 optional Rust importer의 모든 edge-case 동등성;
- JSON/XML/SQLite의 모든 primitive type과 timezone round-trip equality;
- 동일 timestamp의 복수 object attribute change 순서 의미;
- malformed 또는 dangling relation의 모든 variant별 동작;
- 실제 dataset에서 representation drift 또는 silent loss가 발생하는 빈도;
- 두 객체 모델의 대규모 memory와 처리량;
- 모든 유효 OCEL 2.0 instance에 대한 strict conformance;
- OCEL 2.0 XML example과 XSD relation element 불일치의 최종 공식 해석.

검증되지 않은 성공률, 손실 빈도, 성능 및 정확도 수치는 알 수 없음이다.

---

## 12. 유효기간과 철회 조건

이 비교는 다음 기준선에 유효하다.

```text
OCEL:  Specification Version 2.0, document date 2023-10-16
OCPA:  de056e0203a3fa4a9bbc19a95e001eada323074a
PM4Py: 3329bbcbadce8764f7df660fd88636c30793fbd0
```

다음 경우 관련 판단을 재검토하거나 철회한다.

- OCEL 2.0 공식 errata 또는 후속 표준이 relation/object-change 의미를 변경한 경우;
- OCPA가 standard JSON importer를 추가한 경우;
- OCPA가 representation invariant와 source-ID mapping을 강제한 경우;
- OCPA가 E2O/O2O를 multi-relation structure로 변경한 경우;
- OCPA가 canonical input과 graph/cache를 분리한 경우;
- PM4Py가 disconnected event/object를 보존하도록 filtering contract를 변경한 경우;
- PM4Py가 import 시 schema·semantic validation과 structured loss report를 제공한
  경우;
- 어느 library든 immutable evidence-preserving OCEL contract를 도입한 경우;
- runtime round-trip 또는 mutation test가 기존 source 분석을 반증한 경우;
- PIX의 canonical dataset, determinism 또는 evidence-lineage 요구가 변경된 경우.

---

## 13. 최종 평가

**OCEL 2.0은 PIX가 보존해야 할 event, object, type, dynamic attribute 및 qualified
relation의 규범적 의미 기준이다. PM4Py는 이 의미를 독립 relation row와 공통
DataFrame container로 수용하여 reference serialization 대응과 qualifier
multiplicity에서 상대적으로 강하지만, disconnected record 제거와 silent
normalization 때문에 그대로 canonical contract가 될 수 없다. OCPA는
EventGraph·process execution·variant 분석에 직접적인 복합 workspace를 제공하지만
원본과 파생 representation의 identity drift 및 multi-qualifier collapse 위험 때문에
표준 보존 모델로 채택하기 어렵다. PIX는 OCEL 2.0 의미를 독립적으로 구현하고,
PM4Py식 relation 분리를 canonical dataset 설계에 참고하며, OCPA식 graph와
process execution은 검증된 versioned derived computation으로만 도입해야 한다.**
