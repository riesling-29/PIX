<!-- 한국어 버전 -->

# OCPA 전체 구조 분석

**문서 유형:** Upstream 참조 분석 / 전체 구조 기준선

**대상 프로젝트:** PIX

**참조 라이브러리:** OCPA

**참조 저장소:** `https://github.com/ocpm/ocpa.git`

**분석 브랜치:** `main`

**분석 커밋:** `de056e0203a3fa4a9bbc19a95e001eada323074a`

**OCPA 버전:** `1.3.3`

**분석일:** 2026-07-23

**상태:** 소스 구조 분석 기준선

---

## 0. 목적과 범위

이 문서는 PIX가 OCPA에서 무엇을 참조·조정·재구현하거나 사용하지 않을지 결정하기 전에 OCPA의 저장소 구조와 주요 실행 경로를 기록한다.

분석 범위는 다음과 같다.

1. 저장소와 installable package 구조
2. 공개 API 구성 방식
3. algorithm·factory·version dispatch 패턴
4. 주요 event log 및 process model 객체
5. 대표 import, discovery, conformance, variant 실행 경로
6. 의존성 경계와 PM4Py 결합
7. 입력과 결과 contract
8. test, example, documentation 구조
9. PIX에 대한 예비 시사점

이 문서는 모든 OCPA 알고리즘의 정확성이나 성능을 입증하지 않는다. Runtime test, 대규모 dataset 성능, 표준 준수, 배포 라이선스 호환성은 소스 구조 분석만으로 확정할 수 없다.

---

## 1. 분석 기준

### 1.1 확인된 저장소 상태

```text
Repository: ocpm/ocpa
Remote:     https://github.com/ocpm/ocpa.git
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3
```

검사 당시 upstream checkout에는 로컬 Git 변경 사항이 없었다. 최근 commit은 2025-03-19에 `correlated_event_graphs` 관련 코드를 제거한 변경이다.

### 1.2 확인된 소스 규모

`ocpa` package 아래에는 Python 파일 202개가 있었다.

| 영역 | Python 파일 수 | 논리적 줄 수 | 주요 책임 |
| --- | ---: | ---: | --- |
| `ocpa/algo` | 106 | 8,366 | Discovery, conformance, enhancement, predictive monitoring 및 공통 algorithm |
| `ocpa/objects` | 70 | 3,422 | OCEL, graph, OCPN, action-oriented process management object |
| `ocpa/visualization` | 21 | 1,065 | OCPN, variant, constraint graph, alignment 시각화 |
| `ocpa/util` | 4 | 123 | 상수와 일부 공통 utility |
| 합계 | 201 | 12,976 | 최상위 `ocpa/__init__.py`를 제외한 영역 합계 |

파일 수와 줄 수는 물리적 구조를 설명할 뿐 코드 품질, test coverage 또는 기능 중요도를 측정한 값은 아니다.

### 1.3 라이선스 metadata 충돌

저장소의 라이선스 표시는 서로 일치하지 않는다.

```text
setup.py:    license="MIT"
LICENSE.txt: GNU GENERAL PUBLIC LICENSE Version 3
```

따라서 이 저장소의 법적 배포 라이선스를 소스 검사만으로 하나로 확정할 수 없다. PIX가 OCPA 소스를 직접 재사용할 수 있는지는 **알 수 없음**이며, upstream maintainer의 명시적 설명 또는 authoritative package metadata 확인이 필요하다. 구조 연구와 코드 재사용은 별개의 결정으로 취급해야 한다.

---

## 2. 최상위 저장소 구조

```text
ocpa-upstream/
├── .github/                 # CI 및 clone-count workflow
├── docs/                    # Sphinx/Read the Docs 문서 소스
├── example-scripts/         # 실행 예제
├── ocpa/                    # 설치 가능한 Python package
├── ocpa.egg-info/           # 설치 metadata 산출물
├── sample_logs/             # JSON-OCEL 및 OCEL 2.0 sample
├── tests/                   # pytest test module
├── CLONE.md
├── environment.yml
├── LICENSE.txt
├── README.md
├── requirements.txt
└── setup.py
```

Packaging 진입점은 `setup.py`다. `ocpa/__init__.py`에서 package name, version, author metadata를 읽는다.

`setup.py`의 `install_requires`는 다음 세 항목만 선언한다.

```text
pm4py==2.2.32
setuptools
jsonschema
```

반면 `requirements.txt`는 Graphviz, lxml, Matplotlib, NetworkX, NumPy, Pandas, PM4Py, seaborn, tqdm, multiset 등을 고정 version으로 선언한다. 따라서 package metadata만 설치했을 때와 requirements file을 사용했을 때의 환경이 동일하다고 단정할 수 없다.

---

## 3. 설치 가능한 패키지 구조

OCPA는 최상위 facade function을 대량 re-export하지 않는다. `ocpa/__init__.py`는 version과 author metadata만 제공하며, 사용자는 기능 package의 `factory.py` 또는 `algorithm.py`를 직접 import한다.

```text
ocpa/
├── __init__.py
├── algo/
│   ├── conformance/
│   ├── discovery/
│   ├── enhancement/
│   ├── ocel2_use_cases/
│   ├── predictive_monitoring/
│   └── util/
├── objects/
│   ├── aopm/
│   ├── graph/
│   ├── log/
│   └── oc_petri_net/
├── visualization/
│   ├── alignment_viz/
│   ├── constraint_graph/
│   ├── log/
│   └── oc_petri_net/
└── util/
```

대표 사용자 호출 형태는 다음과 같다.

```python
from ocpa.objects.log.importer.ocel import factory as ocel_import_factory
from ocpa.algo.discovery.ocpn import algorithm as ocpn_discovery_factory

ocel = ocel_import_factory.apply("sample.jsonocel")
ocpn = ocpn_discovery_factory.apply(ocel)
```

PM4Py의 `import pm4py; pm4py.read_*()` facade와 달리 OCPA의 공개 surface는 package path와 `apply()` convention에 더 직접적으로 노출된다.

---

## 4. 주요 내부 패키지

### 4.1 `ocpa.algo`

`algo`는 OCPA source의 기능 중심이다.

```text
algo/
├── conformance/
│   ├── alignments/
│   ├── constraint_monitoring/
│   ├── precision_and_fitness/
│   └── token_based_replay/
├── discovery/
│   ├── enhanced_ocpn/
│   └── ocpn/
├── enhancement/
│   ├── event_graph_based_performance/
│   ├── ocpn_analysis/
│   └── token_replay_based_performance/
├── ocel2_use_cases/
├── predictive_monitoring/
└── util/
    ├── aopm/
    ├── filtering/
    ├── process_executions/
    ├── retrieval/
    └── variants/
```

파일 수 기준으로는 `algo/util` 36개, `conformance` 26개, `enhancement` 21개, `predictive_monitoring` 10개, `discovery` 8개다.

### 4.2 `ocpa.objects`

`objects`에는 data representation뿐 아니라 계산용 cache와 mutable process model도 포함된다.

```text
objects/
├── log/                     # OCEL composite와 import/export/conversion
├── graph/                   # Event, object, process-execution, constraint graph
├── oc_petri_net/            # ObjectCentricPetriNet 및 marking
└── aopm/                    # Action interface/impact/action engine model
```

`objects/log`는 하나의 canonical representation만 제공하지 않는다. 같은 log를 다음 형태로 동시에 보관한다.

```text
Table                  # Pandas DataFrame 중심
ObjectCentricEventLog  # Event/Obj dictionary 중심
EventGraph             # NetworkX event graph
ObjectGraph            # 선택적 O2O graph
ObjectChangeTable      # 선택적 object-change DataFrame 집합
```

### 4.3 `ocpa.visualization`

시각화는 OCPN, object-centric variant, constraint graph, alignment 결과를 다룬다. Graphviz, Matplotlib, NetworkX에 직접 의존한다.

### 4.4 `ocpa.util`

최상위 utility는 작지만 algorithm-specific utility가 `ocpa/algo/util` 아래에 집중되어 있다. 이에 따라 이름상 `util`이 반드시 low-level 무의존 계층을 뜻하지는 않는다.

---

## 5. Algorithm과 version dispatch 패턴

검사한 package에는 다음이 있었다.

```text
algorithm.py 파일: 16
factory.py 파일:   12
versions 디렉터리: 19
variants 디렉터리: 6
```

일반적인 pattern은 다음과 같다.

```text
사용자 import
→ factory.py 또는 algorithm.py
→ string constant
→ VERSIONS dictionary
→ versions/<implementation>.py
→ apply(..., parameters=dict)
```

대표 형태는 다음과 같다.

```python
VERSIONS = {
    "connected_components": connected_components.apply,
    "leading_type": leading_type.apply,
}


def apply(ocel, variant="connected_components", parameters=None):
    return VERSIONS[variant](ocel, parameters=parameters)
```

### 5.1 장점

- Algorithm family와 implementation variant를 분리한다.
- String key로 구현을 교체할 수 있다.
- Public caller가 implementation module을 직접 알 필요는 없다.
- Process execution, variant, discovery, importer가 비슷한 convention을 공유한다.

### 5.2 구조적 비용

- `apply()`와 open `parameters` dictionary만으로 semantic contract를 알기 어렵다.
- Variant key가 string이므로 잘못된 값은 runtime dictionary lookup에서 실패한다.
- Parameter validation이 family마다 다르다.
- Operator identity, version, source reference가 result에 포함되지 않는다.
- `unavailable`, `invalid_input`, `unsupported` 상태가 공통 result로 표준화되어 있지 않다.
- 일부 importer의 `variant` parameter는 source comment에서 제거 예정으로 표시되어 있다.

---

## 6. 대표 실행 경로

### 6.1 Classic JSON-OCEL import

```text
ocpa.objects.log.importer.ocel.factory.apply
→ VERSIONS["ocel_json"]
→ import_ocel_json.apply
→ JSON dictionary parsing
→ Event / Obj / MetaObjectCentricData / RawObjectCentricData
→ ObjectCentricEventLog
→ jsonocel_to_csv conversion
→ Table
→ event-object graph 생성
→ OCEL(Table, ObjectCentricEventLog, EventGraph, parameters)
```

한 file import가 entity dictionary, DataFrame, graph를 모두 생성한다.

### 6.2 CSV import

```text
CSV
→ to_df.apply
→ object-type column cell을 list로 parsing
→ internal event_id 생성 및 timestamp sort
→ Table
→ df_to_ocel.apply
→ ObjectCentricEventLog
→ eog_from_log
→ EventGraph
→ OCEL
```

CSV importer는 기본적으로 원본 event ID column을 사용하지 않고 row 수에 따라 string ID를 새로 만든다.

### 6.3 Process execution extraction

`OCEL.process_executions`는 처음 접근할 때 lazy computation을 실행한다.

```text
OCEL.process_executions
→ process_executions.factory.apply
→ connected_components 또는 leading_type
→ EventGraph와 Table projection
→ process execution event set
→ process execution object set
→ event-to-execution mapping
```

기본 방식은 event-object graph의 weakly connected component다. `leading_type` 방식은 지정된 object type을 case anchor로 사용한다.

### 6.4 Variant calculation

`OCEL.variants`도 처음 접근할 때 계산된다.

```text
OCEL.variants
→ variants.factory.apply
→ two_phase 또는 one_phase
→ process-execution graph projection
→ Weisfeiler-Lehman graph hash
→ 선택적 exact isomorphism refinement
→ variant list, frequency, graph, execution mapping
```

Two-phase variant 계산은 중간 column인 `event_objects`를 log DataFrame에 추가했다가 제거하고, 최종적으로 `event_variant` column을 log에 기록한다. 따라서 lazy query가 내부 Table을 변경할 수 있다.

### 6.5 Object-Centric Petri Net discovery

```text
OCEL / ObjectCentricEventLog / DataFrame
→ ocpn.algorithm.apply
→ DataFrame normalization
→ object type별 traditional log projection
→ PM4Py Inductive Miner
→ object type별 Petri net
→ 공통 activity label transition merge
→ ObjectCentricPetriNet
```

OCPA의 OCPN discovery는 PM4Py `2.2.32`의 Inductive Miner와 Petri-net utility를 직접 사용한다. OCPA 독립 알고리즘만으로 완결된 경로가 아니다.

### 6.6 Conformance

대표 result 형태는 다음과 같이 서로 다르다.

```text
precision_and_fitness.apply → (precision, fitness) tuple
constraint_monitoring.apply → boolean과 diagnostic 또는 diagnostic list
token_based_replay.apply    → variant별 native result
```

공통 computation envelope는 없다.

---

## 7. 주요 데이터와 모델 객체

### 7.1 Composite `OCEL`

OCPA의 최상위 `OCEL`은 mutable dataclass다.

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

`process_executions`, `variants`와 관련 mapping은 private cache로 두고 property 접근 시 lazy하게 계산한다.

### 7.2 Entity representation

`ObjectCentricEventLog`는 다음 계층을 가진다.

```text
ObjectCentricEventLog
├── meta: MetaObjectCentricData
└── raw: RawObjectCentricData
    ├── events: dict[event_id, Event]
    ├── objects: dict[object_id, Obj]
    └── obj_event_mapping
```

`Event`는 `id`, `act`, `time`, `omap`, `vmap`을 가지고, `Obj`는 `id`, `type`, `ovmap`을 가진다.

### 7.3 Table representation

`Table`은 전달된 DataFrame을 복사하고 `event_id`를 index로 설정한다. 빠른 lookup을 위한 NumPy array, column mapping, event-to-value mapping을 추가로 만든다.

`remove_object_references()` 같은 helper는 in-place로 table을 변경하며, source comment는 모든 representation의 consistency를 보장하지 않는 quick helper라고 명시한다.

### 7.4 Graph representation

`EventGraph`와 `ObjectGraph`는 NetworkX graph wrapper다.

```text
EventGraph.eog     → nx.DiGraph
ObjectGraph.graph  → nx.DiGraph
```

`ObjectChangeTable`은 object type별 Pandas DataFrame dictionary를 보관한다.

### 7.5 Object-Centric Petri Net

`ObjectCentricPetriNet`은 Place, Transition, Arc를 내부 class로 정의한다. Place는 object type과 initial/final flag를, Arc는 variable flag와 weight를 가진다. Model은 mutable set과 mapping을 보관하고 add/remove operation을 제공한다.

---

## 8. 객체 중심 기능의 분포

OCPA는 객체 중심 분석 자체가 주목적인 라이브러리이므로 객체 중심 기능이 package 전반을 구성한다.

```text
objects/log
    OCEL representation, importer, exporter, converter

algo/util/process_executions
    객체 중심 case extraction

algo/util/variants
    graph 기반 variant

algo/discovery/ocpn
    Object-Centric Petri Net discovery

algo/conformance
    alignment, replay, fitness/precision, constraint monitoring

algo/enhancement
    performance 및 OCPN analysis

algo/predictive_monitoring
    event/execution feature extraction과 encoding

visualization
    OCPN, variant, constraint, alignment visualization
```

이 breadth는 OCPA가 좁은 computation kernel이 아니라 범용 object-centric process-analysis toolkit임을 보여준다.

---

## 9. 의존성 경계

### 9.1 외부 의존성

정적 import 검사에서 다음 수의 OCPA Python file이 주요 외부 library를 직접 import했다.

| 외부 package | Import하는 OCPA 파일 수 |
| --- | ---: |
| NetworkX | 24 |
| Pandas | 21 |
| PM4Py | 12 |
| Matplotlib | 6 |
| Graphviz | 4 |
| NumPy | 3 |
| lxml | 3 |

PM4Py는 특히 OCPN discovery, Petri-net model, projection, conformance utility에서 사용된다.

### 9.2 내부 방향

표면적인 방향은 다음과 같다.

```text
importer/converter
    ↓
objects/log
    ↓
algo
    ↓
visualization
```

그러나 실제로는 `OCEL` property가 method 내부에서 `algo.util`을 lazy import하고, algorithm이 object representation을 변경하며, objects와 algo가 서로 결합한다.

따라서 strict one-way layer라기보다 data object와 feature package가 상호 의존하는 modular toolkit에 가깝다.

### 9.3 PIX와의 차이

PIX가 요구하는 방향은 다음과 같다.

```text
contracts
   ↓
compute
   ↓
intelligence
   ↓
projection / API
```

OCPA의 object가 algorithm을 lazy import하고 mutable cache를 보유하는 방식은 PIX의 neutral contract 경계와 직접 호환되지 않는다.

---

## 10. 입력과 결과 contract

### 10.1 입력

OCPA operation은 다음 representation을 받을 수 있다.

- `OCEL`
- `ObjectCentricEventLog`
- Pandas DataFrame
- `ObjectCentricPetriNet`
- Constraint graph
- Feature storage
- Open `parameters` dictionary

입력 type에 따라 facade가 DataFrame conversion 또는 projection을 수행할 수 있다.

### 10.2 결과

결과 type은 family별로 다르다.

- `OCEL`
- `ObjectCentricEventLog`
- Pandas DataFrame
- `ObjectCentricPetriNet`
- tuple
- dictionary
- list
- boolean과 diagnostic의 조합
- numeric precision/fitness
- `Feature_Storage`

다음 정보는 공통으로 강제되지 않는다.

- operator name과 version
- computation ID
- source event/object ID
- normalized-input identity
- assumption
- status
- rejected 또는 unavailable component
- evidence reference
- withdrawal condition

### 10.3 Unknown과 failure

Operation에 따라 `ValueError`, generic `Exception`, dictionary lookup failure, empty collection 또는 native boolean을 사용할 수 있다. Empty result와 unavailable computation 사이의 공통 의미는 없다.

---

## 11. Test, example, documentation

### 11.1 확인된 물리 구조

저장소에는 다음이 있다.

```text
Python test file:       3
활성 test function:     4
Python example script: 26
sample log file:       10
```

Sample log 구성은 다음과 같다.

| 확장자 | 파일 수 |
| --- | ---: |
| `.jsonocel` | 5 |
| `.sqlite` | 3 |
| `.xmlocel` | 1 |
| `.xml` | 1 |

### 11.2 CI

GitHub Actions workflow는 Python 3.9에서 다음을 실행하도록 정의되어 있다.

```text
pip install -r requirements.txt
pip install -e .
flake8
pytest tests/*.py
```

현재 로컬 환경에서는 `py` launcher가 없고 발견된 `python` 환경에는 `pytest`가 설치되어 있지 않아 test를 실행하지 못했다. 따라서 이 commit의 실제 현재 pass rate와 coverage는 **알 수 없음**이다.

### 11.3 Documentation drift

현재 source에서 제거된 `correlated_event_graph` 관련 RST 문서가 `docs/source`에는 남아 있다. 최신 commit의 제거 내용과 documentation tree가 완전히 동기화됐다고 볼 수 없다.

---

## 12. 아키텍처 특성

### 12.1 확인된 구조적 사실

- OCPA는 객체 중심 process mining 전용 Python library다.
- 최상위 convenience facade보다 feature-level factory와 algorithm import를 사용한다.
- `factory/algorithm → VERSIONS → implementation.apply` 패턴을 반복한다.
- OCEL은 Table, entity dictionary, EventGraph를 동시에 보관한다.
- Process execution과 variant는 lazy하게 계산되고 OCEL 내부에 cache된다.
- OCPN discovery는 PM4Py에 직접 의존한다.
- Object-centric discovery, conformance, enhancement, prediction, visualization을 한 package에서 제공한다.
- Result type과 failure state는 algorithm family별로 다르다.

### 12.2 데이터 기반 해석

OCPA는 **여러 동기화된 representation을 이용하는 object-centric process-analysis toolkit**으로 규정하는 것이 타당하다.

근거는 다음과 같다.

1. 같은 log를 DataFrame, entity dictionary, graph로 동시에 materialize한다.
2. Object-centric case와 variant를 graph 계산으로 lazy 생성한다.
3. OCPN discovery와 conformance가 PM4Py primitive를 조합한다.
4. Feature package별 factory와 native result를 유지한다.
5. Strict layer보다 feature 조합과 분석 breadth를 우선한다.

후속 runtime 검증에서 representation 사이의 자동 consistency enforcement가 확인되면 “동기화 책임이 명시적이지 않다”는 관련 해석을 재검토해야 한다.

---

## 13. PIX 계승에 대한 예비 시사점

### 13.1 참조할 가치가 있는 패턴

1. **Event·object·graph를 함께 고려하는 object-centric semantics**
2. **Connected-component와 leading-object process execution projection**
3. **Graph hash와 isomorphism을 이용한 variant 계산**
4. **Object type별 traditional projection을 조합한 OCPN discovery**
5. **E2O뿐 아니라 O2O와 object change를 별도 representation으로 유지**
6. **실제 sample log와 end-to-end example**

### 13.2 PIX에서 재설계가 필요한 패턴

1. **한 dataset의 여러 mutable representation**
2. **Object가 algorithm을 lazy import하는 양방향 결합**
3. **Open parameter dictionary와 string variant**
4. **Lazy query가 내부 DataFrame을 변경하는 동작**
5. **Heterogeneous native result**
6. **Source/evidence reference가 없는 computation**
7. **Unavailable과 empty result의 미구분**
8. **PM4Py version에 고정된 direct algorithm dependency**
9. **해결되지 않은 repository license metadata**

### 13.3 예비 adaptation mapping

| OCPA 개념 | 가능한 PIX 해석 | 필요한 강화 |
| --- | --- | --- |
| `OCEL` composite | `ProcessDataset`과 derived view | canonical immutable input과 derived-cache 분리 |
| `Table` | tabular compute backend | public mutation 차단 및 cache invalidation |
| `ObjectCentricEventLog` | event/object contract | tuple·mapping 기반 neutral contract |
| `EventGraph` | object projection result | source relation과 projection assumption 기록 |
| process execution | trace/process-instance projection | operator version과 source IDs 포함 |
| variant calculation | optional compute operator | deterministic normalization contract |
| OCPN discovery | future external adapter | PIX v0.1 scope 밖 |
| constraint monitoring | finding generation 참조 | computation-linked finding contract |
| factory/versions | operator dispatcher | typed config와 explicit status |

이 mapping은 설계 후보이며 승인된 PIX 구현 결정이 아니다.

---

## 14. 미확인 사항

다음은 현재 소스 검사만으로는 **알 수 없음**이다.

- 실제 현재 test pass rate와 coverage
- Python 3.11 이상에서의 완전한 호환성
- PM4Py `2.2.32` 이외 version에서의 호환성
- 대규모 OCEL에서 여러 representation의 memory overhead
- Lazy variant 계산의 deterministic behavior와 timeout 재현성
- 모든 algorithm의 malformed-input behavior
- OCEL 2.0 importer의 완전한 표준 준수
- 라이선스 metadata 충돌의 authoritative resolution
- PIX v0.1에서 OCPA algorithm을 직접 사용할 실익
- Schumpeter mission log에 대한 process-execution projection의 적합성

---

## 15. 유효기간과 철회 조건

### 15.1 유효기간

이 분석은 다음 commit에 유효하다.

```text
de056e0203a3fa4a9bbc19a95e001eada323074a
```

비교 없이 이후 OCPA release에도 동일한 판단을 적용해서는 안 된다.

### 15.2 철회 조건

다음 경우 관련 판단을 재검토하거나 철회한다.

- 최상위 facade 또는 typed operator API가 도입된 경우
- OCEL representation이 하나의 canonical immutable model로 통합된 경우
- Representation consistency가 자동으로 강제되는 경우
- 공통 computation-result contract가 추가된 경우
- PM4Py direct dependency가 제거되거나 지원 version 범위가 변경된 경우
- OCEL 2.0 I/O surface가 확대된 경우
- Test와 runtime execution이 source-derived call path를 반증하는 경우
- Upstream이 authoritative license를 명확히 한 경우
- PIX가 좁은 audit engine에서 범용 object-centric mining platform으로 바뀐 경우

---

## 16. 최종 평가

**OCPA 1.3.3은 `feature-level factory/algorithm → string variant → implementation.apply` 패턴과 `Table + entity dictionary + graph`의 복합 OCEL representation을 사용하는 범용 object-centric process-analysis toolkit이다. Process execution, variant, OCPN discovery, conformance 및 performance 분석은 PIX에 유용한 의미론적 참조지만, 여러 mutable representation, PM4Py direct dependency, open parameter dictionary, heterogeneous result, 불명확한 failure state와 license metadata 충돌은 PIX의 evidence-first deterministic contract에 그대로 사용할 수 없다.**

---

<!-- English version -->

# OCPA overall structure analysis

**Document type:** Upstream reference analysis / whole structure baseline

**Target project:** PIX

**Reference library:** OCPA

**Reference repository:** `https://github.com/ocpm/ocpa.git`

**Analysis branch:** `main`

**Analysis commit:** `de056e0203a3fa4a9bbc19a95e001eada323074a`

**OCPA Version:** `1.3.3`

**Analysis date:** 2026-07-23

**Status:** source-structure analysis baseline

---

## 0. Purpose and scope

This document PIXYou go. OCPABefore deciding whether or not to use OCPAIt records the storage structure and the main runway.

The scope of analysis is as follows:

1. Storage and installable package structure
2. Public API configuration method
3. Algorithm factory version dispatch pattern
4. Main event log and process model objects
5. Representative import, discovery, conformance, variant runway
6. Dependence boundaries and PM4Py combined
7. Input and result contract
8. test, example, documentation structure
9. Preliminary checkpoint for the PIX

This document does not prove the accuracy or performance of all OCPA algorithms. Runtime testing, large-scale dataset performance, standard compliance, and distribution license compatibility cannot be verified by source structure analysis alone.

---

## 1. Analysis baseline

### 1.1 Confirmed repository state

```text
Repository: ocpm/ocpa
Remote:     https://github.com/ocpm/ocpa.git
Branch:     main
Commit:     de056e0203a3fa4a9bbc19a95e001eada323074a
Version:    1.3.3
```

At the time of inspection there were no changes to the local Git upstream checkout. The most recent commit is a change that removed the `correlated_event_graphs` related code on 2025-03-19.

### 1.2 Confirmed source size

Below the `ocpa` package were 202 Python files.

| The realm | Python number of files | It's logical. | Key Responsibilities |
| --- | ---: | ---: | --- |
| `ocpa/algo` | 106 | 8,366 | Discovery, conformance, enhancement, predictive monitoring and common algorithm |
| `ocpa/objects` | 70 | 3,422 | OCEL, graph, OCPN, action-oriented process management object |
| `ocpa/visualization` | 21 | 1,065 | OCPN, variant, constraint graph, alignment visualization |
| `ocpa/util` | 4 | 123 | Variable and some common utility |
| That's the total. | 201 | 12,976 | Total area excluding top `ocpa/__init__.py` |

The number and number of files describe the physical structure, but not the code quality, test coverage or functional significance.

### 1.3 License metadata collisions

The license sign of the repository does not match each other.

```text
setup.py:    license="MIT"
LICENSE.txt: GNU GENERAL PUBLIC LICENSE Version 3
```

Therefore, the legal distribution of these repositories cannot be confirmed by a single source inspection. Where PIX can directly reuse the OCPA source is **unknown**, an explicit description of the upstream maintainer or authoritative package metadata verification is required. Structural research and code reuse should be treated as separate decisions.

---

## 2. Top of the line storage.

```text
ocpa-upstream/
├── .github/                 # CI 및 clone-count workflow
├── docs/                    # Sphinx/Read the Docs 문서 소스
├── example-scripts/         # 실행 예제
├── ocpa/                    # 설치 가능한 Python package
├── ocpa.egg-info/           # 설치 metadata 산출물
├── sample_logs/             # JSON-OCEL 및 OCEL 2.0 sample
├── tests/                   # pytest test module
├── CLONE.md
├── environment.yml
├── LICENSE.txt
├── README.md
├── requirements.txt
└── setup.py
```

Packaging entrance is `setup.py`. I read the package name, version, author metadata from `ocpa/__init__.py`.

`setup.py`'s `install_requires` declares only the following three items.

```text
pm4py==2.2.32
setuptools
jsonschema
```

`requirements.txt`, on the other hand, declares Graphviz, lxml, Matplotlib, NetworkX, NumPy, Pandas, PM4Py, seaborn, tqdm, multiset and others as fixed versions. Therefore, it is not possible to determine that the environment is the same when only the package metadata is installed and when the requirements file is used.

---

## 3. Installable package architecture

OCPA does not mass re-export the top facade function. `ocpa/__init__.py` provides only version and author metadata, and users directly import the `factory.py` or `algorithm.py` of the feature package.

```text
ocpa/
├── __init__.py
├── algo/
│   ├── conformance/
│   ├── discovery/
│   ├── enhancement/
│   ├── ocel2_use_cases/
│   ├── predictive_monitoring/
│   └── util/
├── objects/
│   ├── aopm/
│   ├── graph/
│   ├── log/
│   └── oc_petri_net/
├── visualization/
│   ├── alignment_viz/
│   ├── constraint_graph/
│   ├── log/
│   └── oc_petri_net/
└── util/
```

The representative user call form is as follows:

```python
from ocpa.objects.log.importer.ocel import factory as ocel_import_factory
from ocpa.algo.discovery.ocpn import algorithm as ocpn_discovery_factory

ocel = ocel_import_factory.apply("sample.jsonocel")
ocpn = ocpn_discovery_factory.apply(ocel)
```

PM4Pyof `import pm4py; pm4py.read_*()` Unlike the facade. OCPAThe open surface of the package path and the `apply()` It's more directly exposed to convention.

---

## 4. The main internal package.

### 4.1 `ocpa.algo`

`algo` is the functional center of the OCPA source.

```text
algo/
├── conformance/
│   ├── alignments/
│   ├── constraint_monitoring/
│   ├── precision_and_fitness/
│   └── token_based_replay/
├── discovery/
│   ├── enhanced_ocpn/
│   └── ocpn/
├── enhancement/
│   ├── event_graph_based_performance/
│   ├── ocpn_analysis/
│   └── token_replay_based_performance/
├── ocel2_use_cases/
├── predictive_monitoring/
└── util/
    ├── aopm/
    ├── filtering/
    ├── process_executions/
    ├── retrieval/
    └── variants/
```

According to the number of files, there are 36 `algo/util`, 26 `conformance`, 21 `enhancement`, 10 `predictive_monitoring` and 8 `discovery`.

### 4.2 `ocpa.objects`

`objects` includes not only data representation but also computational cache and mutable process model.

```text
objects/
├── log/                     # OCEL composite와 import/export/conversion
├── graph/                   # Event, object, process-execution, constraint graph
├── oc_petri_net/            # ObjectCentricPetriNet 및 marking
└── aopm/                    # Action interface/impact/action engine model
```

`objects/log` does not provide a single canonical representation. Keep the same log in the following form at the same time.

```text
Table                  # Pandas DataFrame 중심
ObjectCentricEventLog  # Event/Obj dictionary 중심
EventGraph             # NetworkX event graph
ObjectGraph            # 선택적 O2O graph
ObjectChangeTable      # 선택적 object-change DataFrame 집합
```

### 4.3 `ocpa.visualization`

Visualization deals with OCPN, object-centric variant, constraint graph, and alignment results. It relies directly on Graphviz, Matplotlib, NetworkX.

### 4.4 `ocpa.util`

The top utility is small, but algorithm-specific utility is concentrated below `ocpa/algo/util`. Accordingly, the `util` in the name does not necessarily mean a low-level non-existent hierarchy.

---

## 5. Algorithm and version dispatch pattern

The package we checked was:

```text
algorithm.py 파일: 16
factory.py 파일:   12
versions 디렉터리: 19
variants 디렉터리: 6
```

The general pattern is as follows:

```text
사용자 import
→ factory.py 또는 algorithm.py
→ string constant
→ VERSIONS dictionary
→ versions/<implementation>.py
→ apply(..., parameters=dict)
```

The representative form is as follows:

```python
VERSIONS = {
    "connected_components": connected_components.apply,
    "leading_type": leading_type.apply,
}


def apply(ocel, variant="connected_components", parameters=None):
    return VERSIONS[variant](ocel, parameters=parameters)
```

### 5.1 points

- Separates the algorithm family from the implementation variant.
- You can replace the implementation with a string key.
- Public callers don't have to know the implementation module themselves.
- Process execution, variant, discovery, and importer share a similar convention.

### 5.2 Structural costs

- `apply()` and the open `parameters` dictionary alone make it difficult to understand semantic contracts.
- Because the variant key is a string, the wrong value fails in the runtime dictionary lookup.
- Parameter validation varies by family.
- Operator identity, version, and source reference are not included in the result.
- `unavailable`, `invalid_input`, `unsupported` Status are not standardized as a common result.
- The `variant` parameter of some importers is shown to be removed from the source comment.

---

## 6. Representative runway

### 6.1 Classic JSON-OCEL import

```text
ocpa.objects.log.importer.ocel.factory.apply
→ VERSIONS["ocel_json"]
→ import_ocel_json.apply
→ JSON dictionary parsing
→ Event / Obj / MetaObjectCentricData / RawObjectCentricData
→ ObjectCentricEventLog
→ jsonocel_to_csv conversion
→ Table
→ event-object graph 생성
→ OCEL(Table, ObjectCentricEventLog, EventGraph, parameters)
```

A file import creates an entity dictionary, DataFrame, and a graph.

### 6.2 CSV import

```text
CSV
→ to_df.apply
→ object-type column cell을 list로 parsing
→ internal event_id 생성 및 timestamp sort
→ Table
→ df_to_ocel.apply
→ ObjectCentricEventLog
→ eog_from_log
→ EventGraph
→ OCEL
```

CSV importer basically does not use the original event ID column but creates a new string ID based on the row number.

### 6.3 Process execution extraction

`OCEL.process_executions` performs lazy computation when first approached.

```text
OCEL.process_executions
→ process_executions.factory.apply
→ connected_components 또는 leading_type
→ EventGraph와 Table projection
→ process execution event set
→ process execution object set
→ event-to-execution mapping
```

The default method is the weakly connected component of the event-object graph. The `leading_type` method uses a specified object type as a case anchor.

### 6.4 Variant calculation

`OCEL.variants` is also calculated when first approached.

```text
OCEL.variants
→ variants.factory.apply
→ two_phase 또는 one_phase
→ process-execution graph projection
→ Weisfeiler-Lehman graph hash
→ 선택적 exact isomorphism refinement
→ variant list, frequency, graph, execution mapping
```

The two-phase variant calculation adds the middle column `event_objects` to the log DataFrame and removes it, and finally records the `event_variant` column to the log. So lazy query can change the inner Table.

### 6.5 Object-Centric Petri Net discovery

```text
OCEL / ObjectCentricEventLog / DataFrame
→ ocpn.algorithm.apply
→ DataFrame normalization
→ object type별 traditional log projection
→ PM4Py Inductive Miner
→ object type별 Petri net
→ 공통 activity label transition merge
→ ObjectCentricPetriNet
```

OCPAThe discovery of the OCPN PM4Py `2.2.32`It uses the Inductive Miner and Petri-net utility directly. OCPA is not an independent algorithm.

### 6.6 Conformance

The representative result forms differ as follows:

```text
precision_and_fitness.apply → (precision, fitness) tuple
constraint_monitoring.apply → boolean과 diagnostic 또는 diagnostic list
token_based_replay.apply    → variant별 native result
```

There is no common computation envelope.

---

## 7. Major data and model objects

### 7.1 Composite `OCEL`

OCPA's highest `OCEL` is the mutable dataclass.

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

`process_executions`, `variants` and related mapping use private cache to calculate lazy access to property.

### 7.2 Entity representation

`ObjectCentricEventLog` has the next layer.

```text
ObjectCentricEventLog
├── meta: MetaObjectCentricData
└── raw: RawObjectCentricData
    ├── events: dict[event_id, Event]
    ├── objects: dict[object_id, Obj]
    └── obj_event_mapping
```

`Event` has `id`, `act`, `time`, `omap`, `vmap`, and `Obj` has `id`, `type`, and `ovmap`.

### 7.3 Table representation

`Table` copies the transmitted DataFrame and sets the `event_id` as an index. It adds NumPy array, column mapping, event-to-value mapping for quick lookup.

A helper like `remove_object_references()` changes the table in-place, and the source comment specifies that it is a quick helper that does not guarantee the consistency of all representations.

### 7.4 Graph representation

`EventGraph` and `ObjectGraph` are NetworkX graph wrappers.

```text
EventGraph.eog     → nx.DiGraph
ObjectGraph.graph  → nx.DiGraph
```

`ObjectChangeTable` maintains the Pandas DataFrame dictionary by object type.

### 7.5 Object-Centric Petri Net

`ObjectCentricPetriNet` defines Place, Transition, and Arc as an internal class. Place has object type and initial/final flag, and Arc has variable flag and weight. Model stores the mutable set and mapping and provides the add/remove operation.

---

## 8. Distribution of object-centered functions

OCPA is a notable library of object-centered analysis itself, so object-centered functions constitute the package as a whole.

```text
objects/log
    OCEL representation, importer, exporter, converter

algo/util/process_executions
    객체 중심 case extraction

algo/util/variants
    graph 기반 variant

algo/discovery/ocpn
    Object-Centric Petri Net discovery

algo/conformance
    alignment, replay, fitness/precision, constraint monitoring

algo/enhancement
    performance 및 OCPN analysis

algo/predictive_monitoring
    event/execution feature extraction과 encoding

visualization
    OCPN, variant, constraint, alignment visualization
```

This breadth shows that OCPA is not a narrow computation kernel, but a universal object-centric process-analysis toolkit.

---

## 9. Dependence boundaries

### 9.1 External dependence

In the static import check the following number of OCPA Python files directly imported the main external library.

| External package | The number of OCPA files imported |
| --- | ---: |
| NetworkX | 24 |
| Pandas | 21 |
| PM4Py | 12 |
| Matplotlib | 6 |
| Graphviz | 4 |
| NumPy | 3 |
| lxml | 3 |

PM4Py is particularly used in OCPN discovery, Petri-net model, projection, and conformance utility.

### 9.2 Inward direction

The surface direction is as follows:

```text
importer/converter
    ↓
objects/log
    ↓
algo
    ↓
visualization
```

However, in reality, the `OCEL` property lazy import `algo.util` from within the method, the algorithm changes the object representation, and objects and algo combine with each other.

It's therefore closer to a modular toolkit where data objects and feature packages depend on each other than a strict one-way layer.

### 9.3 Difference with PIX

The direction PIX demands is as follows:

```text
contracts
   ↓
compute
   ↓
intelligence
   ↓
projection / API
```

The way OCPA's object lazy imports the algorithm and holds a mutable cache is not directly compatible with PIX's neutral contract boundaries.

---

## 10. Input and result contract

### 10.1 Input

The OCPA operation can receive the following representation.

- `OCEL`
- `ObjectCentricEventLog`
- Pandas DataFrame
- `ObjectCentricPetriNet`
- Constraint graph
- Feature storage
- Open `parameters` dictionary

Depending on the type of input the facade can perform a DataFrame conversion or projection.

### The result is 10.2.

The resulting type varies by family.

- `OCEL`
- `ObjectCentricEventLog`
- Pandas DataFrame
- `ObjectCentricPetriNet`
- tuple
- dictionary
- list
- A combination of boolean and diagnostic
- numeric precision/fitness
- `Feature_Storage`

The following information is not mandatory in common.

- Operator name and version
- computation ID
- source event/object ID
- normalized-input identity
- assumption
- status
- Rejected or unavailable component
- evidence reference
- withdrawal condition

### 10.3 Unknown and failure

`ValueError`, generic `Exception`, dictionary lookup failure, empty collection or native boolean can be used depending on the operation. There is no common meaning between empty result and unavailable computation.

---

## 11. Test, example, documentation

### 11.1 Confirmed physical structure

There's this in the warehouse.

```text
Python test file:       3
활성 test function:     4
Python example script: 26
sample log file:       10
```

The sample log configuration is as follows:

| Expanders | Number of files |
| --- | ---: |
| `.jsonocel` | 5 |
| `.sqlite` | 3 |
| `.xmlocel` | 1 |
| `.xml` | 1 |

### 11.2 CI

GitHub Actions workflow is defined in Python 3.9 to run the following:

```text
pip install -r requirements.txt
pip install -e .
flake8
pytest tests/*.py
```

In today's local environment, `py` There was no launcher. `python` It's the environment. `pytest`I couldn't run the test because it wasn't installed. Therefore, the actual current pass rate and coverage of this commit is **unknown**.

### 11.3 Documentation drift

`correlated_event_graph` related RST documents that have been removed from the current source remain in `docs/source`. I can't see the removal of the latest commit and the documentation tree being completely synced.

---

## 12. Architectural characteristics

### 12.1 Confirmed structural facts

- OCPA is the Python library dedicated to object-centered process mining.
- It uses feature-level factory and algorithm import rather than top-level convenience facade.
- Repeat the `factory/algorithm → VERSIONS → implementation.apply` pattern.
- OCEL stores Table, entity dictionary, and EventGraph at the same time.
- Process execution and variant are lazyly calculated and cached inside OCEL.
- OCPN discovery is directly dependent on PM4Py.
- It provides object-centric discovery, conformance, enhancement, prediction, and visualization in one package.
- The result type and failure state are different for each algorithm family.

### 12.2 Data-based interpretation

OCPA should be defined as an object-centric process-analysis toolkit using several synchronized representations.

The basis is as follows:

1. The same log is simultaneously materialized as DataFrame, entity dictionary, and graph.
2. Object-centric case and variant generate lazy by graph computation.
3. OCPN discovery and conformance combine the PM4Py primitive.
4. Feature package by factory and native result.
5. They prefer feature combinations and analytical breadth over strict layers.

If automatic consistency enforcement between representation is confirmed in a subsequent runtime verification, then the relevant interpretation should be re-examined.

---

## 13. Preliminary checkpoint for the PIX successor

### 13.1 Patterns worth seeing

1. **Object-centric semantics that consider the event-object-graph together**
2. **Connected-component and leading-object process execution projection**
3. *Variant calculations using graph hash and isomorphism*
4. The OCPN discovery combines traditional projection for each object type.
5. **Keep E2O and O2O and object change as distinct representation**
6. **Real sample log and end-to-end example**

### 13.2 PIX is a pattern that needs to be redesigned.

1. **Multiple mutable representation of a single dataset**
2. The object's lazy import of the algorithm.
3. **Open parameter dictionary and string variant**
4. **Lazy query changes the internal DataFrame**
5. **Heterogeneous native result**
6. "Source/evidence reference-free computation"
7. **Unavailable and empty result subdivision**
8. **Direct algorithm dependency fixed to the ZPM4Py version**
9. **Unresolved repository license metadata**

### 13.3 Preliminary adaptation mapping

| OCPA concept | The possible interpretation of PIX | We need reinforcements. |
| --- | --- | --- |
| `OCEL` composite | `ProcessDataset` and derived view | canonical immutable input and derived-cache separation |
| `Table` | tabular compute backend | Public mutation blocking and cache invalidation |
| `ObjectCentricEventLog` | event/object contract | Tuple·mapping-based neutral contract |
| `EventGraph` | object projection result | Source relation and projection assumption record |
| process execution | trace/process-instance projection | Includes operator version and source IDs |
| variant calculation | optional compute operator | deterministic normalization contract |
| OCPN discovery | future external adapter | PIX v0.1 out of scope |
| constraint monitoring | See finding generation | computation-linked finding contract |
| factory/versions | operator dispatcher | Typed config and explicit status |

This mapping is a design candidate and not an approved PIX implementation decision.

---

## 14. Uncertainties

The following is **unknown** for current source testing only.

- Actual current test pass rate and coverage
- Full compatibility with Python 3.11 and above
- PM4Py `2.2.32` compatibility with other versions
- memory overhead of multiple representation in a large OCEL
- The deterministic behavior of the lazy variant calculation and the timeout reproduction
- Malformed-input behavior of all algorithms
- Full compliance with the OCEL 2.0 importer standard
- Authoritative resolution of conflict of license metadata
- In PIX v0.1 you can use the OCPA algorithm directly.
- The compatibility of the process-execution projection for the Schumpeter mission log

---

## 15. Validity and Withdrawal Conditions

### 15.1 Validity

This analysis is valid for the following commit.

```text
de056e0203a3fa4a9bbc19a95e001eada323074a
```

The same judgment should not apply to subsequent OCPA releases without comparison.

### 15.2 Withdrawal conditions

In the following cases, the relevant judgments shall be reviewed or withdrawn.

- If the top facade or typed operator API is introduced
- If the OCEL representation is integrated into one canonical immutable model,
- If the representation consistency is automatically enforced,
- If a common computation-result contract is added,
- PM4Py if direct dependency is removed or the supported version range is changed
- OCEL 2.0 If the I/O surface is enlarged
- If the test and runtime execution contradict the source-derived call path,
- If upstream made clear the authoritative license,
- If PIX is changed from a narrow audit engine to a universal object-centric mining platform,

---

## 16. The final evaluation

**OCPA 1.3.3 is a general purpose object-centric process-analysis toolkit that uses `feature-level factory/algorithm → string variant → implementation.apply` pattern and `Table + entity dictionary + graph`'s complex OCEL representation. Process execution, variant, OCPN discovery, conformance and performance analysis are useful semantic references to PIX, but several mutable representation, PM4Py direct dependency, open parameter dictionary, heterogeneous result, uncertain failure state and license metadata conflicts cannot be used as such in PIX's evidence-first deterministic contract.**
