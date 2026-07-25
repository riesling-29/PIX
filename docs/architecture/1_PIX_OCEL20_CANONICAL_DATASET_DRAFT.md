# PIX OCEL 2.0 Canonical Dataset 및 OCPA·PM4Py 상호운용 초안

**문서 유형:** Architecture decision proposal / canonical data contract draft

**대상 프로젝트:** PIX

**초안 버전:** 0.1

**작성일:** 2026-07-25

**상태:** 검토 전 초안. 승인된 architecture baseline이 아님

---

## 0. 결정하려는 문제

PIX는 다음 입력을 하나의 중립적인 데이터 계약으로 수용할 필요가 있다.

1. OCEL 2.0 JSON, XML 및 SQLite
2. PM4Py의 in-memory `OCEL`
3. OCPA의 in-memory `OCEL`
4. 두 library가 지원하는 legacy 또는 확장 파일 형식

동시에 같은 PIX dataset에서 필요에 따라 PM4Py 또는 OCPA용 객체를 만들어 각 library의 알고리즘을 사용할 수 있어야 한다.

여기서 “합집합”은 두 library의 모든 field를 하나의 mutable 객체에 평면적으로 복사한다는 뜻으로 사용하지 않는다. 이 초안에서 합집합은 다음 세 계층의 결합이다.

```text
OCEL 2.0 standard canonical facts
    +
명시적으로 격리된 upstream extension facts
    +
버전과 입력 근거를 가진 derived computations
```

정본은 첫 번째 계층뿐이다. 두 번째와 세 번째 계층은 정본의 의미를 변경할 수 없다.

---

## 1. 먼저 구분해야 하는 사실과 판단

### 1.1 확인된 사실

OCEL 2.0 Specification Version 2.0의 Definition 2는 OCEL을 다음 tuple로 정의한다.

```text
L = (
    E, O, EA, OA,
    evtype, time, objtype,
    eatype, oatype,
    eaval, oaval,
    E2O, O2O
)
```

핵심 의미는 다음과 같다.

- 모든 event는 event type과 timestamp를 가진다.
- 모든 object는 object type을 가진다.
- Event attribute는 해당 event type에 속한다.
- Object attribute는 해당 object type에 속하며 값은 시간에 따라 변할 수 있다.
- E2O는 `(event, qualifier, object)`의 집합이다.
- O2O는 `(source object, qualifier, target object)`의 집합이다.
- Event 또는 object는 E2O에 연결되지 않아도 존재할 수 있다.
- E2E, EventGraph, process execution 및 variant는 Definition 2의 구성 요소가 아니다.

### 1.2 확인된 upstream 차이

- PM4Py는 event, object, E2O, O2O 및 object change를 독립 DataFrame으로 표현한다.
- PM4Py에는 E2E DataFrame이 있지만 E2E는 OCEL 2.0 Definition 2의 표준 구성 요소가 아니다.
- PM4Py의 검사된 import 경로는 relation filtering을 전파하면서 disconnected event와 object를 제거할 수 있다.
- OCPA는 `Table`, entity dictionary, `EventGraph`, 선택적 `ObjectGraph`와 change table을 결합한다.
- OCPA의 검사된 경로에는 representation별 ID 차이, object 누락 및 같은 endpoint의 복수 qualifier 축약 가능성이 있다.
- 두 library 모두 structured import-loss report를 기본 계약으로 제공하지 않는다.

### 1.3 이 초안의 설계 판단

PIX 정본은 OCPA 또는 PM4Py 객체가 아니라 immutable `Ocel20Dataset`이어야 한다.

근거는 다음과 같다.

- 어느 한 library의 object를 정본으로 삼으면 다른 library가 표현하지 못하는 정보가 정본 단계에서 손실될 수 있다.
- OCPA의 분석용 graph/cache와 PM4Py의 denormalized relation metadata는 OCEL 2.0 원천 사실과 수명주기가 다르다.
- PIX의 기존 architecture는 deterministic process facts, evidence lineage 및 explicit unavailable state를 요구한다.

이 판단은 다음 조건에서 철회하거나 수정한다.

- 한 upstream library가 Definition 2 전체, source identity, immutable semantics 및 structured loss report를 함께 보장하는 정본 계약을 제공한다.
- PIX가 source identity와 deterministic replay를 더 이상 요구하지 않는다.
- 실제 vertical slice에서 별도 canonical dataset이 유의미한 결함 예방 없이 adapter 복잡도만 증가시킨다는 반증이 축적된다.

---

## 2. 제안하는 architecture

```text
Source artifact / upstream OCEL object
                │
                ▼
        Source-specific extractor
                │
                ▼
         ParsedOcelRecords
                │
        syntax + semantic validation
                │
                ▼
         DatasetImportResult
                │
        valid dataset만 승격
                ▼
       Ocel20Dataset  ← PIX canonical source of truth
          │       │
          │       ├───────────────┐
          ▼                       ▼
 PM4Py disposable view      OCPA disposable view
          │                       │
          └──────────┬────────────┘
                     ▼
          versioned computation result
```

Library view에서 계산된 결과는 입력 dataset identity, operator, version, parameter 및 사용한 adapter report를 인용해야 한다. View 자체는 다시 canonical dataset에 병합하지 않는다. 병합이 필요하면 새 import transaction으로 처리한다.

---

## 3. 표준 적합성 원칙

### 3.1 Canonical core는 Definition 2만 따른다

`Ocel20Dataset`에 허용하는 의미 요소는 다음뿐이다.

```text
Event
Object
EventType
ObjectType
EventAttributeDefinition
ObjectAttributeDefinition
EventAttributeValue
ObjectAttributeValue
EventObjectRelation
ObjectObjectRelation
```

다음은 canonical core에 넣지 않는다.

```text
E2E relation
EventGraph
ObjectGraph cache
Process execution
Variant
Flattened trace
PM4Py relation의 denormalized activity/timestamp/object-type column
OCPA Table의 object-type별 convenience column
Library parameter 또는 mutable cache
```

### 3.2 표준보다 강한 PIX profile

OCEL 2.0 metamodel 적합성과 PIX 계산 재현성은 같은 개념이 아니다. 따라서 PIX는 표준을 변경하지 않으면서 다음 강화 규칙을 추가한다.

- Dataset과 record는 immutable value로 취급한다.
- Canonical serialization과 content digest를 위한 deterministic ordering을 정의한다.
- Timestamp를 비교 가능한 instant로 해석할 수 없으면 가정을 명시하기 전까지 canonical 승격을 중단한다.
- Source identifier와 canonical identifier의 mapping을 남긴다.
- Normalization, coercion, inference, rejection 및 omission을 구조화된 record로 남긴다.
- Invalid, unsupported, unavailable 및 empty-valid를 서로 다른 상태로 유지한다.

이 규칙은 OCEL 2.0 표준 자체의 요구사항이라고 주장하지 않는다. `PIX OCEL20 Profile 0.1`의 추가 invariant다.

### 3.3 표준 적합성 표현

PIX 내부 판정은 다음처럼 분리한다.

```text
syntax_conformance
    특정 JSON Schema, XML XSD 또는 SQLite profile에 대한 구문 판정

metamodel_conformance
    Definition 2 의미 및 invariant에 대한 판정

pix_profile_conformance
    immutability, deterministic time, identity와 evidence 규칙에 대한 판정

target_adaptation_conformance
    특정 OCPA/PM4Py view로 요구 의미를 보존할 수 있는지에 대한 판정
```

`parser가 읽음`, `schema-valid`, `OCEL 2.0 의미 보존` 및 `특정 library에서 lossless`를 같은 status로 합치지 않는다.

---

## 4. Canonical object model

아래 코드는 구현 확정본이 아니라 field와 불변식을 검토하기 위한 Python-like contract다.

### 4.1 Identifier와 primitive value

```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar


@dataclass(frozen=True, order=True)
class EventId:
    value: str


@dataclass(frozen=True, order=True)
class ObjectId:
    value: str


@dataclass(frozen=True, order=True)
class EventTypeId:
    value: str


@dataclass(frozen=True, order=True)
class ObjectTypeId:
    value: str


@dataclass(frozen=True, order=True)
class AttributeId:
    value: str


class OcelValueType(str, Enum):
    STRING = "string"
    TIME = "time"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


OcelValue = str | datetime | int | float | bool
```

`EventId("x")`와 `ObjectId("x")`는 lexical value가 같아도 다른 tagged universe에 속한다. 이는 Definition 1의 event/object universe 분리를 코드 수준에서 보존하기 위한 장치다.

`None`, arbitrary Python object, DataFrame, list 및 dict는 canonical attribute value로 허용하지 않는다. Null 또는 복합 source value는 parsing record에는 남길 수 있지만, 명시적인 변환 또는 rejection 없이 canonical value가 될 수 없다.

### 4.2 Time

```python
@dataclass(frozen=True)
class OcelTime:
    initial: bool
    instant: datetime | None
```

불변식은 다음과 같다.

- `OcelTime(initial=True)`는 Definition 2의 `0`을 나타내며 `instant`는 `None`이다.
- `initial=False`이면 `instant`가 반드시 존재한다.
- Instant는 PIX profile에서 비교 가능한 timezone-aware 값이다.
- Initial time은 모든 instant보다 앞선다.
- Source timestamp에 timezone이 없으면 importer는 임의 timezone을 조용히 부여하지 않는다.
- 명시적 import policy가 timezone을 공급한 경우에만 변환하고 assumption record를 남긴다.

### 4.3 Type 및 attribute definition

```python
@dataclass(frozen=True)
class EventAttributeDefinition:
    attribute_id: AttributeId
    event_type_id: EventTypeId
    value_type: OcelValueType


@dataclass(frozen=True)
class ObjectAttributeDefinition:
    attribute_id: AttributeId
    object_type_id: ObjectTypeId
    value_type: OcelValueType


@dataclass(frozen=True)
class EventType:
    event_type_id: EventTypeId
    attributes: tuple[EventAttributeDefinition, ...]


@dataclass(frozen=True)
class ObjectType:
    object_type_id: ObjectTypeId
    attributes: tuple[ObjectAttributeDefinition, ...]
```

동일 `AttributeId`를 여러 event/object type에 중복 선언하지 않는다. Event type과 object type 사이의 중복도 허용하지 않는다. Source가 같은 attribute name을 여러 type에서 재사용하여 Definition 2의 attribute-set 조건과 충돌하면 strict import는 실패한다. 이름을 자동 namespace로 바꾸는 것은 의미 변경이므로 recovery policy의 명시적 선택과 mapping 없이는 수행하지 않는다.

### 4.4 Event와 object

```python
@dataclass(frozen=True)
class OcelEvent:
    event_id: EventId
    event_type_id: EventTypeId
    timestamp: OcelTime


@dataclass(frozen=True)
class OcelObject:
    object_id: ObjectId
    object_type_id: ObjectTypeId


@dataclass(frozen=True)
class EventAttributeValue:
    event_id: EventId
    attribute_id: AttributeId
    value: OcelValue
```

Event attribute 값은 해당 event의 type에 선언된 attribute에만 허용한다. `(event_id, attribute_id)`는 canonical dataset 안에서 유일하다. Event와 object record에 mutable mapping을 넣지 않으며, object의 값은 모두 시간 의미를 가진 별도 record로 표현한다.

### 4.5 Object attribute history

```python
@dataclass(frozen=True)
class ObjectAttributeValue:
    object_id: ObjectId
    attribute_id: AttributeId
    effective_at: OcelTime
    value: OcelValue
```

`(object_id, attribute_id, effective_at)`는 canonical dataset 안에서 유일하다. Definition 2의 `oaval`은 partial function이므로 동일 key에 서로 다른 두 값을 허용하지 않는다.

Timestamp가 없는 static value는 `initial=True`로 표현한다. Unix epoch, 최소 Python datetime 또는 첫 event 시간으로 대체하지 않는다.

### 4.6 Qualified relation

```python
@dataclass(frozen=True, order=True)
class Qualifier:
    value: str


@dataclass(frozen=True)
class EventObjectRelation:
    event_id: EventId
    qualifier: Qualifier
    object_id: ObjectId


@dataclass(frozen=True)
class ObjectObjectRelation:
    source_object_id: ObjectId
    qualifier: Qualifier
    target_object_id: ObjectId
```

불변식은 다음과 같다.

- Qualifier는 optional이 아니다.
- E2O identity는 `(event_id, qualifier, object_id)`다.
- O2O identity는 `(source_object_id, qualifier, target_object_id)`다.
- 같은 endpoint에 qualifier가 여러 개이면 모두 별도 relation으로 보존한다.
- O2O 방향을 보존한다.
- 모든 endpoint는 dataset 내부에 존재해야 한다.
- Exact duplicate triple은 canonical set에 두 번 들어갈 수 없다.
- Event 또는 object가 어느 E2O에도 참여하지 않아도 제거하지 않는다.

Legacy source에 qualifier가 없으면 strict import는 canonical 승격을 중단한다. Recovery mode에서 `pix:unspecified` 같은 실제 qualifier를 합성할 수 있으나, 이는 표준 필드를 채운 synthetic semantics이므로 caller의 명시적 정책과 `InferredField` record가 필요하다.

### 4.7 Dataset

```python
@dataclass(frozen=True)
class Ocel20Dataset:
    contract_version: str
    event_types: tuple[EventType, ...]
    object_types: tuple[ObjectType, ...]
    events: tuple[OcelEvent, ...]
    objects: tuple[OcelObject, ...]
    event_attribute_values: tuple[EventAttributeValue, ...]
    object_attribute_values: tuple[ObjectAttributeValue, ...]
    event_object_relations: tuple[EventObjectRelation, ...]
    object_object_relations: tuple[ObjectObjectRelation, ...]
    content_digest: str
```

`contract_version`은 PIX contract version이지 OCEL standard version을 대체하지 않는다. 최초 후보는 다음과 같다.

```text
pix.ocel20.dataset/0.1
```

`content_digest`는 provenance와 source file path가 아니라 canonical semantic content로 계산한다. 같은 의미의 JSON, XML 및 SQLite가 동일하게 canonicalize되면 같은 digest를 가져야 한다. 이 동등성은 구현 후 cross-format fixture로 검증하기 전까지 목표 invariant이지 확인된 구현 사실이 아니다.

---

## 5. Dataset invariant

Canonical 승격 전 최소한 다음을 모두 검사한다.

### 5.1 Identity

- Event ID는 event universe 안에서 유일하다.
- Object ID는 object universe 안에서 유일하다.
- Event와 object는 각각 존재하는 type을 가리킨다.
- Source ID mapping은 source namespace 안에서 역추적 가능하다.
- 서로 다른 source dataset을 merge할 때 lexical ID 충돌을 조용히 덮어쓰지 않는다. 동일 entity임을 입증하거나 namespace 기반 canonical ID와 mapping을 사용한다.

### 5.2 Attribute

- Attribute definition은 정확히 하나의 허용 owner type을 가진다.
- Event attribute value의 owner type과 declared type이 일치한다.
- Object attribute value의 owner type과 declared type이 일치한다.
- Value runtime type이 definition의 `OcelValueType`과 일치한다.
- Null, unknown primitive 및 동일 object-attribute-time 중복은 canonical core에 없다.

Python에서는 `bool`이 `int`의 subtype이므로 type validator는 `True`를 integer로 수용하지 않도록 exact semantic type을 검사해야 한다.

### 5.3 Time

- 모든 event timestamp는 deterministic하게 비교 가능하다.
- Object attribute history에는 initial 또는 실제 timestamp가 있다.
- 같은 object-attribute에 값이 여러 개면 time ordering을 계산할 수 있다.

### 5.4 Relation

- 모든 E2O/O2O endpoint가 존재한다.
- 모든 relation에 qualifier가 있다.
- Exact duplicate triple이 없다.
- Disconnected event/object를 invalid로 취급하거나 제거하지 않는다.

### 5.5 Deterministic canonical order

Tuple의 저장 순서는 의미 집합과 별개로 다음 기준을 사용한다.

```text
event types:             event_type_id
object types:            object_type_id
events:                  timestamp, event_id
objects:                 object_type_id, object_id
event attribute values:  event_id, attribute_id
object attribute values: object_id, attribute_id, effective_at
E2O:                     event_id, qualifier, object_id
O2O:                     source_object_id, qualifier, target_object_id
```

동일 timestamp의 event 순서는 event ID로 안정화하되, 이것을 실제 인과 순서로 해석하지 않는다.

---

## 6. Import transaction과 evidence contract

### 6.1 Parsing과 canonical 승격을 분리한다

```text
SourceArtifact
    ↓ format-specific parsing
ParsedOcelRecords
    ↓ syntax validation
    ↓ OCEL 2.0 semantic validation
    ↓ explicit normalization/recovery policy
Ocel20Dataset 또는 no dataset
```

Parser가 일부 record를 읽었다는 이유만으로 불완전 dataset을 성공 결과로 반환하지 않는다.

### 6.2 Import result

```python
T = TypeVar("T")


class ImportStatus(str, Enum):
    VALID = "valid"
    RECOVERED = "recovered"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    statement: str
    source_reference: str | None
    affected_ids: tuple[str, ...]
    withdrawal_condition: str | None


@dataclass(frozen=True)
class IdentifierMapping:
    source_namespace: str
    entity_kind: str
    source_id: str
    canonical_id: str


@dataclass(frozen=True)
class TransformationRecord:
    kind: str
    field: str
    source_value: object
    canonical_value: object
    reason: str
    assumption: str | None


@dataclass(frozen=True)
class DatasetImportResult:
    status: ImportStatus
    source_format: str
    source_format_version: str | None
    syntax_profile: str | None
    dataset: Ocel20Dataset | None
    identifier_mappings: tuple[IdentifierMapping, ...]
    validation_issues: tuple[ValidationIssue, ...]
    transformations: tuple[TransformationRecord, ...]
    rejected_records: tuple[object, ...]
    omitted_components: tuple[str, ...]
    source_references: tuple[str, ...]
    assumptions: tuple[str, ...]
```

### 6.3 Default import policy

기본값은 `strict`다.

```text
strict
    추론이나 의미 변경 없이 표준 canonical dataset을 만들 수 있을 때만 VALID

recover
    caller가 허용한 변환만 수행하고 모든 변환을 기록

inspect
    parsing과 issue 수집만 수행하며 canonical dataset을 만들지 않음
```

`recover` 결과의 dataset도 4절과 5절의 canonical invariant를 모두 만족해야 한다. 만족하지 못하면 `RECOVERED`가 아니라 `INVALID`다.

---

## 7. Source adapter 규칙

### 7.1 OCEL 2.0 JSON, XML 및 SQLite

각 reference serialization은 동일 pipeline으로 수렴한다.

```text
format syntax validation
    ↓
role별 parsed record
    ↓
Definition 2 semantic validation
    ↓
Ocel20Dataset
```

구문 validator와 parser는 분리한다. XML은 검사한 Specification artifact에서 relationship child 표현의 불일치가 있으므로, 다음 상태를 구분한다.

- 실제 사용한 XSD에 valid
- Compatibility parser가 읽었지만 XSD 결과는 invalid 또는 unknown
- Metamodel에는 승격 가능

Compatibility parse를 XSD conformance로 보고하지 않는다.

### 7.2 PM4Py `OCEL`에서 import

Primary facts는 다음 table에서 읽는다.

```text
events
objects
relations
o2o
object_changes
```

규칙은 다음과 같다.

- `relations`의 event ID, object ID 및 qualifier를 E2O source로 사용한다.
- `relations`의 denormalized activity, timestamp 및 object type은 primary fact가 아니라 consistency check 대상으로만 사용한다.
- `e2e`는 canonical core로 가져오지 않는다.
- Disconnected event/object를 relation propagation으로 제거하지 않는다.
- `propagate_relations_filtering` 같은 destructive normalization을 canonicalization 전에 호출하지 않는다.
- Caller가 소유한 PM4Py object를 mutate하지 않고 snapshot으로 읽는다.
- `object_changes`와 object base attribute를 모두 Definition 2의 temporal object value로 변환한다.
- Base value와 change value의 temporal ordering을 결정할 근거가 없으면 issue를 남기고 strict 승격을 중단한다.

PM4Py `e2e`가 필요하면 9절의 namespaced auxiliary fact로 보관할 수 있다.

### 7.3 OCPA `OCEL`에서 import

OCPA object는 여러 representation이 하나의 logical log를 중복 표현할 수 있으므로 다음 원칙을 사용한다.

```text
Source file을 다시 읽을 수 있음
    → source artifact adapter를 우선

OCPA object만 있음
    → representation consistency audit
    → 합의되는 facts만 canonical 후보로 사용
    → 충돌은 기본적으로 INVALID
```

검사 대상은 최소 다음과 같다.

- `Table`과 entity view의 event ID, type, timestamp 및 E2O endpoint
- `EventGraph` node ID와 event universe
- `ObjectGraph`의 O2O endpoint와 qualifier
- Change table의 object ID, attribute 및 timestamp
- Same-endpoint multi-qualifier가 어느 representation에서 축약됐는지

OCPA entity ID와 Table ID가 다르면 한쪽을 조용히 선택하지 않는다. Source mapping으로 동일성을 입증하거나 caller가 authority policy를 지정해야 한다.

OCPA representation에서 E2O qualifier를 복원할 수 없으면 strict import는 실패한다. Endpoint만 일치한다는 사실은 qualifier 동일성의 근거가 아니다.

### 7.4 Legacy 및 library-specific 파일

CSV, classic JSON, classic XML, compact CSV, bundle 또는 Parquet source는 “OCEL 2.0 파일”이라고 자동 분류하지 않는다. 대신 다음처럼 처리한다.

```text
legacy/extension syntax
    ↓ source-specific parsed records
    ↓ 필요한 type, qualifier, timestamp policy
    ↓ OCEL 2.0 semantic validation
    ↓ canonical 승격 여부 판정
```

따라서 source format이 비표준이어도 결과 dataset은 OCEL 2.0 metamodel에 맞을 수 있다. 반대로 parser가 `.jsonocel`을 읽었다고 해서 결과가 자동으로 OCEL 2.0 conformant인 것은 아니다.

---

## 8. PM4Py 및 OCPA로 보내는 adapter

### 8.1 공통 adaptation result

```python
class Fidelity(str, Enum):
    LOSSLESS = "lossless"
    LOSSY = "lossy"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CapabilityRequirement:
    component: str
    required: bool


@dataclass(frozen=True)
class AdaptationResult(Generic[T]):
    value: T | None
    fidelity: Fidelity
    source_dataset_digest: str
    target_name: str
    target_version: str
    preserved_components: tuple[str, ...]
    omitted_components: tuple[str, ...]
    synthesized_fields: tuple[str, ...]
    identifier_mappings: tuple[IdentifierMapping, ...]
    validation_issues: tuple[ValidationIssue, ...]
```

Caller는 알고리즘이 요구하는 component를 선언할 수 있어야 한다. 필수 component를 target이 보존하지 못하면 default는 lossy view 생성이 아니라 `UNSUPPORTED` 반환이다.

### 8.2 PM4Py view

PM4Py view 생성 후보 규칙은 다음과 같다.

- Canonical event, object, E2O, O2O 및 object history에서 DataFrame을 직접 만든다.
- Relation의 denormalized activity, timestamp 및 object type은 canonical table join으로 생성한다.
- Disconnected event/object를 유지한다.
- View 생성 뒤 primary table과 denormalized relation metadata를 교차 검증한다.
- PM4Py의 consistency/filtering 함수가 caller dataset을 바꾸지 않도록 disposable copy만 넘긴다.
- PM4Py algorithm 수행 전후 row/component digest를 비교하여 예상하지 못한 mutation을 report한다.

검사된 모델 범위에서는 PM4Py가 OCPA보다 Definition 2를 더 직접적으로 표현한다. 그러나 이를 PM4Py 전체의 strict conformance 보장으로 확대하지 않는다.

### 8.3 OCPA view

OCPA view는 분석 목적별 capability profile을 먼저 선택한다.

```text
event_table_projection
event_graph_projection
object_graph_projection
object_change_projection
```

생성 규칙은 다음과 같다.

- Canonical ID를 유지하는 별도 mapping을 제공한다.
- Object type 이름을 raw DataFrame attribute/column access에 직접 의존하지 않고 reversible safe column key로 encode한다.
- Entity, Table 및 graph를 각각 만든 뒤 ID와 component count invariant를 검증한다.
- EventGraph는 canonical E2O와 timestamp에서 파생한다.
- O2O는 directed qualified triple에서 파생한다.
- 같은 endpoint의 복수 qualifier를 target structure가 보존하지 못하면 `LOSSY` 또는 `UNSUPPORTED`다.
- Disconnected object를 OCPA entity view가 표현하지 못해도 canonical dataset에서는 유지한다.
- Process execution과 variant는 OCPA object의 정본 field로 재수용하지 않고 computation result로 반환한다.

OCPA 알고리즘이 qualifier, disconnected object 또는 exact source identity를 사용하지 않는다는 조건이 입증되면 제한된 lossy view를 허용할 수 있다. 조건이 입증되지 않으면 사용 가능하다고 가정하지 않는다.

### 8.4 Capability matrix 초안

| 의미 요소 | PIX canonical | PM4Py view 후보 | OCPA view 후보 |
| --- | --- | --- | --- |
| Event / event type / time | 표준 정본 | 직접 표현 | 복수 representation, 검증 필요 |
| Object / object type | 표준 정본 | 직접 표현 | disconnected object 누락 방지 필요 |
| Typed event attribute | 표준 정본 | 직접 표현 | type 및 representation 검증 필요 |
| Temporal object attribute | 표준 정본 | base + changes로 투영 | change table 투영, 검증 필요 |
| Qualified E2O triple | 표준 정본 | 독립 relation row | endpoint/qualifier 축약 가능 |
| Qualified directed O2O triple | 표준 정본 | 독립 relation row | graph edge 축약 가능 |
| Disconnected event/object | 보존 | custom view에서 보존 | 일부 view에서 표현 불가 가능 |
| E2E | 표준 정본 아님 | auxiliary로 가능 | 확인된 core field 없음 |
| EventGraph | derived computation | 필요 시 계산 | view에 materialize |
| Process execution / variant | derived computation | algorithm result | algorithm result/cache |

표의 “후보”는 구현 검증 전의 설계 가능성을 의미한다. 실제 round-trip acceptance test가 실패하면 해당 capability를 하향 조정한다.

---

## 9. Upstream extension과 derived result

### 9.1 Canonical core 밖의 auxiliary fact

표준 밖의 source fact를 버리지 않기 위해 다음 sidecar를 둘 수 있다.

```python
@dataclass(frozen=True)
class AuxiliaryFact:
    namespace: str
    fact_type: str
    payload: object
    source_references: tuple[str, ...]


@dataclass(frozen=True)
class OcelInteropBundle:
    canonical: Ocel20Dataset
    auxiliary_facts: tuple[AuxiliaryFact, ...]
```

예:

```text
pm4py:e2e
source:global-metadata
source:unparsed-attribute
```

Auxiliary fact는 다음 제약을 가진다.

- `Ocel20Dataset`의 표준 의미를 덮어쓰지 않는다.
- Standard exporter는 기본적으로 auxiliary fact를 내보내지 않는다.
- Namespace와 serialization policy가 없으면 opaque evidence로만 취급한다.
- PIX operator는 명시적으로 요청하지 않는 한 auxiliary fact를 계산 입력으로 사용하지 않는다.

### 9.2 Derived computation

OCPA에서 유용한 EventGraph, process execution 및 variant는 다음처럼 결과 계약에 둔다.

```python
@dataclass(frozen=True)
class DerivedComputation:
    computation_id: str
    source_dataset_digest: str
    operator_name: str
    operator_version: str
    parameters: tuple[tuple[str, object], ...]
    status: str
    value: object | None
    source_event_ids: tuple[EventId, ...]
    source_object_ids: tuple[ObjectId, ...]
    adapter_report_ref: str | None
    assumptions: tuple[str, ...]
```

같은 dataset이라도 projection rule, leading object type 또는 graph construction parameter가 다르면 다른 computation이다. 따라서 process execution이나 variant를 canonical dataset field로 cache하지 않는다.

---

## 10. Public API 초안

```python
result = pix.ocel.import_file(
    source,
    format="ocel20-json",
    mode="strict",
)
dataset = result.require_valid_dataset()

pm4py_view = pix.interop.pm4py.to_ocel(
    dataset,
    require_fidelity="lossless",
)

ocpa_view = pix.interop.ocpa.to_ocel(
    dataset,
    capabilities=[
        "event_graph_projection",
        "object_change_projection",
    ],
)

variant_result = pix.compute(
    dataset=dataset,
    operator="ocpa_graph_variant",
    adapter=ocpa_view,
)
```

In-memory upstream object import는 별도 entry point를 둔다.

```python
pm_result = pix.interop.pm4py.from_ocel(pm4py_ocel, mode="strict")

ocpa_result = pix.interop.ocpa.from_ocel(
    ocpa_ocel,
    mode="strict",
    representation_policy="fail_on_drift",
)
```

`from_ocel()`은 upstream object를 정본으로 등록하는 함수가 아니라 snapshot을 검증하여 새 `Ocel20Dataset`을 만드는 import transaction이다.

---

## 11. 기존 `ProcessDataset`과의 관계

기존 architecture baseline의 `ProcessDataset`은 다음 필드를 가진 초기 중립 계약이다.

```text
events
objects
event_object_relations
object_object_relations
```

그러나 현재 형태는 다음 OCEL 2.0 의미를 충분히 고정하지 않는다.

- Event/object type별 attribute definition
- Attribute primitive type
- Temporal object attribute history
- `0` 시점의 static object value
- Required qualifier
- Source identity mapping
- Import validation 및 loss evidence

따라서 두 대안이 있다.

### 대안 A - `ProcessDataset`을 `Ocel20Dataset`으로 교체

장점:

- OCEL 2.0 정본임이 API 이름에 드러난다.
- `qualifier: None` 같은 기존 초안의 비표준 상태를 제거하기 쉽다.

비용:

- PIX가 미래에 OCEL 이외의 process dataset을 받으려면 별도 상위 abstraction이 필요하다.

### 대안 B - `ProcessDataset`이 `Ocel20Dataset`을 포함

```python
@dataclass(frozen=True)
class ProcessDataset:
    ocel: Ocel20Dataset
```

장점:

- 기존 PIX public terminology를 유지한다.
- 향후 다른 canonical source family가 필요할 때 확장 여지가 있다.

비용:

- 현재 요구에는 한 단계의 이름과 wrapper가 추가된다.

### 검토 우선순위

현 시점에는 대안 B를 우선 후보로 둔다. 기존 PIX architecture와 API를 유지하면서 OCEL 2.0의 적합성 경계를 분명히 할 수 있기 때문이다.

이 선호는 다음 조건에서 철회한다.

- PIX v0.1의 모든 operator가 오직 OCEL 2.0만 받고 wrapper가 실제 의미 없이 반복되는 경우
- `ProcessDataset`과 `Ocel20Dataset`의 versioning이 불필요하게 분기되는 경우
- 구현 contract test에서 wrapper가 오류 상태나 provenance ownership을 모호하게 만드는 경우

아무 변경도 하지 않는 대안도 가능하다. 다만 기존 `ProcessDataset`을 그대로 유지하면 temporal object value와 required qualifier를 표현할 수 없으므로, 현재 목표인 OCEL 2.0 표준 정본이라는 요구를 충족한다고 판정할 근거가 없다.

---

## 12. 구현 순서 제안

이 문서가 승인되기 전에는 package scaffold나 production adapter를 만들지 않는다. 승인 후에도 다음 최소 순서를 권한다.

### Phase 1 - Contract와 validator

1. Standard core dataclass 또는 equivalent value type
2. Definition 2 semantic validator
3. Deterministic canonical serializer와 digest
4. Import/adaptation result와 issue taxonomy

### Phase 2 - Reference format 한 개

OCEL 2.0 JSON 한 형식만 먼저 구현한다.

검사할 fixture:

- Standard running example
- Disconnected event와 object
- Same endpoint, different qualifier
- Dynamic object attribute
- Same object-attribute-time conflict
- Dangling E2O/O2O
- Missing qualifier
- Naive timestamp
- Duplicate triple

### Phase 3 - PM4Py interop

1. PM4Py object snapshot import
2. Canonical dataset에서 PM4Py view 생성
3. Disconnected component 보존
4. JSON fixture의 semantic round trip
5. Caller object mutation 감지

### Phase 4 - OCPA interop

1. OCPA representation consistency audit
2. Source/canonical ID mapping
3. EventGraph projection
4. O2O/object-change projection
5. Multi-qualifier와 unsafe object-type counterexample
6. Capability-based refusal

### Phase 5 - XML 및 SQLite

Reference serialization별 syntax validation을 추가하되 모든 형식은 같은 metamodel validator와 canonical digest를 사용한다.

---

## 13. Acceptance criteria

### 13.1 Standard core

- Definition 2의 모든 canonical component가 contract에 존재한다.
- E2E, graph, execution 및 variant가 canonical core에 없다.
- Qualifier가 optional이 아니다.
- Disconnected event/object가 보존된다.
- Dynamic object attribute와 initial value를 구분한다.
- Same endpoint의 multiple qualifier가 보존된다.
- O2O 방향이 보존된다.

### 13.2 Evidence

- 모든 ID 변경은 mapping이 있다.
- 모든 type coercion과 inferred value가 transformation record에 있다.
- Rejected/omitted record가 사라지지 않는다.
- Invalid source는 empty-success dataset이 되지 않는다.
- Import와 adaptation status가 구분된다.

### 13.3 Determinism

- 입력 record order가 바뀌어도 같은 의미는 같은 canonical digest를 만든다.
- JSON/XML/SQLite running example이 같은 semantic digest를 만드는지 검사한다.
- 동일 timestamp event의 stable order가 인과 주장으로 사용되지 않는다.

### 13.4 PM4Py

- Disconnected fixture가 PM4Py view 생성 전후 보존된다.
- Denormalized relation metadata가 canonical primary facts와 일치한다.
- View mutation이 canonical dataset을 변경하지 않는다.
- PM4Py object를 다시 import했을 때 canonical component가 loss report 없이 같아야 `LOSSLESS`다.

### 13.5 OCPA

- Table, entity 및 graph ID가 mapping으로 연결된다.
- Object type 이름에 space 또는 identifier-unsafe 문자가 있어도 object가 누락되지 않는다.
- 같은 endpoint의 multiple qualifier를 보존할 수 없으면 `LOSSY` 또는 `UNSUPPORTED`다.
- Disconnected object가 OCPA view에서 누락되더라도 adaptation report에 명시된다.
- Process execution과 variant가 source dataset을 mutate하지 않는 versioned result로 반환된다.

---

## 14. 남아 있는 판단 유보

현재 근거만으로 다음은 알 수 없음이다.

- 대규모 dataset에서 immutable tuple/value-object 구조의 memory 비용
- Pandas/Arrow 기반 internal storage가 dataclass tuple보다 유리한 임계 크기
- OCPA algorithm별로 qualifier 또는 disconnected object loss가 결과에 미치는 빈도
- PM4Py algorithm별 input mutation 범위
- 모든 JSON/XML/SQLite primitive value의 byte-level round-trip
- XML example과 XSD 관계 표현에 대한 공식 errata의 최종 해석
- Same-time object attribute update를 실제 source system들이 얼마나 자주 생성하는지

이 수치와 빈도는 benchmark 및 corpus test 전까지 “알 수 없음”으로 둔다.

---

## 15. 위험과 통제

### 위험 1 - 표준 core와 extension이 다시 섞임

통제:

- `Ocel20Dataset`에는 Definition 2 component만 둔다.
- Auxiliary namespace와 derived computation을 별도 module/package로 둔다.
- Standard serializer가 auxiliary field를 암묵적으로 포함하지 못하게 한다.

### 위험 2 - 두 library를 모두 지원한다는 명목으로 lowest common denominator가 됨

통제:

- Target library가 표현하지 못해도 canonical core에서는 보존한다.
- Adapter가 omission을 기록하고 capability requirement에 따라 거부한다.

### 위험 3 - Recovery mode가 조용한 데이터 조작 경로가 됨

통제:

- Strict를 default로 유지한다.
- Recovery transformation을 allow-list로 제한한다.
- 합성 qualifier, timezone 및 ID에는 source와 assumption을 남긴다.

### 위험 4 - Canonical digest가 provenance 차이를 숨김

통제:

- Semantic content digest와 import transaction/evidence digest를 별도로 둔다.
- 같은 semantic dataset이라도 provenance bundle은 별도로 식별한다.

### 위험 5 - Upstream result를 표준 사실로 오인

통제:

- 모든 library computation은 operator/version/parameter와 adapter report를 인용한다.
- EventGraph edge나 variant를 source OCEL relation으로 역기록하지 않는다.

---

## 16. 근거, 유효기간 및 재검토 조건

### 16.1 근거 기준선

이 초안은 다음 기준에 근거한다.

```text
OCEL 2.0 Specification
Version 2.0
Document date: 2023-10-16

OCPA
Version: 1.3.3
Commit: de056e0203a3fa4a9bbc19a95e001eada323074a

PM4Py
Version: 2.7.23.3
Commit: 3329bbcbadce8764f7df660fd88636c30793fbd0

PIX architecture baseline
Context Baseline v0.1
Date: 2026-07-18
```

참조 분석:

- [OCPA와 PM4Py의 OCEL 객체 이해 방식 비교](../reference-analysis/comparison/0_OCPA_PM4PY_OCEL_OBJECT_MODEL_COMPARISON.md)
- [OCPA와 PM4Py의 파일별 OCEL 생성 과정 및 OCEL 2.0 준수 비교](../reference-analysis/comparison/1_OCPA_PM4PY_OCEL_FILE_IMPORT_AND_OCEL20_COMPLIANCE_COMPARISON.md)
- [OCEL 2.0 Specification](https://www.ocel-standard.org/2.0/ocel20_specification.pdf)

### 16.2 유효기간

이 제안은 위 Specification version과 pinned upstream commit을 기준으로 한 architecture 초안이다. Calendar date만으로 자동 만료시키지는 않지만, 다음 시점에는 재검토한다.

- PIX canonical contract 구현 직전
- OCPA 또는 PM4Py target version 변경 시
- OCEL 표준 errata 또는 후속 version 채택 시
- 첫 cross-format 및 cross-library round-trip 결과 확보 시

### 16.3 판단 철회 조건

다음 반증이 확인되면 관련 판단을 철회하거나 수정한다.

- OCEL 2.0 Definition 2에 E2E, graph 또는 execution을 canonical component로 포함한다는 공식 정정이 발표된다.
- PM4Py가 disconnected record를 기본 보존하고 immutable, loss-reported canonical contract를 제공한다.
- OCPA가 representation identity와 multi-qualified relation을 lossless하게 강제한다.
- Cross-library test에서 별도 canonical model보다 한 upstream object를 정본으로 삼는 방식이 동일한 의미 보존과 더 명확한 evidence를 제공한다.
- `ProcessDataset` wrapper가 실제 operator contract에서 의미적 구분을 만들지 못한다.
- Canonical digest가 reference format 간 동일 의미를 안정적으로 식별하지 못한다.

---

## 17. 제안 결론

**PIX는 `Ocel20Dataset`을 OCEL 2.0 Definition 2에만 기반한 immutable canonical core로 두고, 기존 `ProcessDataset`이 이를 포함하도록 하는 계층형 합집합을 우선 초안으로 채택한다. PM4Py와 OCPA 객체는 canonical source가 아니라 검증·손실 보고가 수반되는 disposable adapter view로 만들며, PM4Py의 E2E는 namespaced auxiliary fact로, OCPA의 EventGraph·process execution·variant는 versioned derived computation으로 격리한다. 이 구조는 두 library 중 한쪽의 표현 한계가 다른 쪽과 PIX의 표준 의미를 손상시키지 않게 하며, 실제 채택 여부는 disconnected record, multi-qualifier, dynamic object attribute, ID drift 및 cross-format digest acceptance test를 통과한 뒤 확정한다.**
