# PM4Py 전체 구조 분석

**문서 유형:** Upstream 참조 분석 / 전체 구조 기준선

**대상 프로젝트:** PIX

**참조 라이브러리:** PM4Py

**참조 저장소:** `D:\ChantaResearchGroup\PIX-References\pm4py-upstream`

**분석 브랜치:** `release`

**분석 커밋:** `3329bbcbadce8764f7df660fd88636c30793fbd0`

**PM4Py 버전:** `2.7.23.3`

**분석일:** 2026-07-19

**상태:** 소스 구조 분석 기준선

---

## 0. 목적과 범위

이 문서는 PIX가 PM4Py에서 무엇을 계승·조정·교체하거나 사용하지 않을지 결정하기 전에 PM4Py의 전체 소스 구조를 기록한다.

분석 범위는 다음과 같다.

1. 저장소와 패키지 구조
2. 공개 API 구성
3. 핵심 알고리즘 dispatch 패턴
4. 주요 데이터 및 프로세스 모델 객체
5. 대표 실행 경로
6. 객체 중심 기능
7. 의존성 경계와 결과 계약
8. 테스트 구조
9. PIX에 대한 예비 시사점

이 문서는 PM4Py의 모든 알고리즘을 평가하지 않는다. 또한 PM4Py 코드를 PIX에 복사할 수 있다고 판단하지 않는다. 실행 성능, 모든 입력에 대한 알고리즘 정확성, 향후 PIX 배포 모델과의 라이선스 호환성은 이 분석에서 검증한 범위 밖이다.

---

## 1. 분석 기준

### 1.1 확인된 저장소 상태

분석은 다음 로컬 checkout을 기준으로 수행했다.

```text
Repository: D:\ChantaResearchGroup\PIX-References\pm4py-upstream
Remote:     https://github.com/process-intelligence-solutions/pm4py.git
Branch:     release
Commit:     3329bbcbadce8764f7df660fd88636c30793fbd0
Version:    2.7.23.3
```

검사 당시 upstream checkout에는 로컬 Git 변경 사항이 없었다.

### 1.2 확인된 소스 파일 수

로컬 트리의 `pm4py` 패키지 아래에는 Python 파일 1,657개가 있었다.

| 영역 | Python 파일 수 | 주요 책임 |
| --- | ---: | --- |
| `pm4py/algo` | 881 | Discovery, conformance, filtering, transformation, evaluation, simulation 알고리즘 |
| `pm4py/objects` | 359 | Event log, OCEL, Petri net, process tree, BPMN, DFG 및 관련 모델 |
| `pm4py/statistics` | 156 | 빈도, 시간, variant, activity 및 객체 중심 통계 |
| `pm4py/visualization` | 142 | Graphviz와 기타 모델·결과 시각화 |
| `pm4py/streaming` | 58 | Streaming import, conversion 및 online 알고리즘 |
| `pm4py/util` | 40 | 상수, parameter 처리, 날짜 parsing, 압축 및 공통 utility |
| 최상위 `pm4py/*.py` | 21 | 사용자 대상 facade 모듈과 패키지 metadata |

이 수치는 물리적 소스 구성을 나타낼 뿐이며 코드 품질, 복잡도 또는 기능 중요도를 측정한 값은 아니다.

### 1.3 라이선스 사실과 해결되지 않은 호환성

검사한 저장소는 open-source edition의 라이선스를 **GNU Affero General Public License version 3(AGPL-3.0)**으로 선언한다. 별도의 commercial license도 제공한다고 명시한다.

PM4Py 소스 코드를 PIX에 포함해도 PIX의 의도된 라이선스 또는 배포 모델이 바뀌지 않는지는 현재 **알 수 없음**이다. 분석 대상 자료에서 PIX의 최종 라이선스와 배포 조건이 정해지지 않았기 때문이다. 따라서 아키텍처 연구와 소스 코드 재사용은 별개의 결정으로 다뤄야 한다.

---

## 2. 최상위 저장소 구조

PM4Py 저장소는 다음과 같이 구성되어 있다.

```text
pm4py-upstream/
├── .github/                 # GitHub 자동화 및 저장소 metadata
├── docs/                    # 문서 소스
├── examples/                # 실행 가능한 사용 예제
├── files/                   # 프로젝트 지원 파일
├── notebooks/               # Notebook 기반 예제와 분석
├── pm4py/                   # 설치 가능한 Python 패키지
├── safety_checks/           # 추가 검사
├── tests/                   # Test runner, fixture, test module
├── third_party/             # Third-party 라이선스 정보
├── README.md
├── CHANGELOG.md
├── COVERAGE.md
├── requirements*.txt
└── setup.py
```

Packaging 진입점은 `setup.py`다. `pm4py/meta.py`에서 버전과 패키지 metadata를 읽고, 이름이 `pm4py`로 시작하는 패키지를 찾으며, `requirements.txt`의 의존성을 설치한다.

주요 runtime 의존성에는 NumPy, Pandas, NetworkX, Graphviz, SciPy, lxml, Matplotlib, pytz, tqdm이 포함된다. 그 밖의 여러 integration은 선택 사항이다.

---

## 3. 설치 가능한 패키지 구조

주 패키지는 서로 다른 두 surface를 가진다.

1. 최상위 사용자 대상 facade 모듈
2. 대규모 내부 구현 패키지

```text
pm4py/
├── __init__.py
├── read.py
├── write.py
├── discovery.py
├── conformance.py
├── filtering.py
├── convert.py
├── analysis.py
├── stats.py
├── ocel.py
├── org.py
├── sim.py
├── vis.py
├── connectors.py
├── llm.py
├── ml.py
├── privacy.py
├── utils.py
│
├── algo/
├── objects/
├── statistics/
├── visualization/
├── streaming/
└── util/
```

### 3.1 최상위 facade 모듈

최상위 모듈은 단순화된 도메인 중심 함수를 제공한다.

| Facade 모듈 | 대표 책임 |
| --- | --- |
| `read.py` | XES, PNML, BPMN, DFG, PTML, OCEL 형식 읽기 |
| `write.py` | Event log와 process model 내보내기 |
| `discovery.py` | DFG, process tree, Petri net, BPMN, Declare 등 발견 |
| `conformance.py` | Token replay, alignment, fitness, precision 및 특수 conformance |
| `filtering.py` | Case, event, path, temporal, variant, OCEL filtering |
| `convert.py` | 지원 representation 사이의 log·process model 변환 |
| `analysis.py` | Soundness 및 구조 분석 |
| `stats.py` | 사용자 대상 통계 query |
| `ocel.py` | 객체 중심 summary, discovery, filtering, enrichment |
| `vis.py` | 사용자 대상 시각화 함수 |

`pm4py/__init__.py`는 이 모듈들을 import하고 많은 함수를 직접 다시 export한다. 의도된 사용 방식은 다음과 같다.

```python
import pm4py

log = pm4py.read_xes("event-log.xes")
tree = pm4py.discover_process_tree_inductive(log)
net, initial_marking, final_marking = pm4py.convert_to_petri_net(tree)
```

Facade는 단순 forwarding 이상의 작업을 한다. 함수에 따라 다음을 수행할 수 있다.

- 필요한 DataFrame column 검증
- 내부 parameter dictionary 구성
- algorithm variant 선택
- 입력 type과 argument 수에 따른 routing
- 입력 또는 출력 representation 변환
- multiprocessing 동작 선택
- 호환성 또는 deprecation warning 출력

### 3.2 Facade 규모

일부 facade 모듈 자체도 상당히 크다.

| 모듈 | 최상위 함수 수 | 대략적인 줄 수 |
| --- | ---: | ---: |
| `discovery.py` | 27 | 1,462 |
| `conformance.py` | 21 | 1,285 |
| `filtering.py` | 41 | 1,852 |
| `stats.py` | 25 | 1,193 |
| `ocel.py` | 27 | 870 |
| `vis.py` | 47 | 1,820 |

따라서 facade는 중요한 아키텍처 계층이지만 항상 얇은 것은 아니다.

---

## 4. 주요 내부 패키지

### 4.1 `pm4py.algo`

`algo`는 가장 큰 패키지이며 PM4Py 기능의 중심이다.

```text
algo/
├── analysis/
├── anonymization/
├── clustering/
├── comparison/
├── concept_drift/
├── conformance/
├── connectors/
├── decision_mining/
├── discovery/
├── evaluation/
├── filtering/
├── label_splitting/
├── merging/
├── organizational_mining/
├── querying/
├── reduction/
├── simulation/
└── transformation/
```

주요 discovery 계열은 다음과 같다.

```text
discovery/
├── alpha/
├── declare/
├── dfg/
├── footprints/
├── genetic/
├── heuristics/
├── ilp/
├── inductive/
├── log_skeleton/
├── ocel/
├── powl/
├── split_miner/
├── temporal_profile/
└── transition_system/
```

주요 conformance 계열은 다음과 같다.

```text
conformance/
├── alignments/
├── antialignments/
├── declare/
├── footprints/
├── log_skeleton/
├── multialignments/
├── ocel/
├── temporal_profile/
└── tokenreplay/
```

### 4.2 `pm4py.objects`

`objects`에는 in-memory representation, model semantics, importer, exporter, conversion이 들어 있다.

```text
objects/
├── log/
├── ocel/
├── petri_net/
├── process_tree/
├── bpmn/
├── dfg/
├── heuristics_net/
├── transition_system/
├── trie/
├── powl/
├── ocpn/
├── oc_causal_net/
├── stochastic_petri/
├── random_variables/
└── conversion/
```

이 패키지는 수동적인 data contract만 담지 않는다. 일부 하위 패키지는 semantics, retrieval, filtering, conversion, importer, exporter 동작도 포함한다.

### 4.3 `pm4py.statistics`

Statistics 패키지는 재사용 가능한 process fact를 계산한다.

- activity와 attribute 빈도
- 시작·종료 activity
- variant
- directly/eventually-following behavior
- service time과 sojourn time
- overlap, concurrency, rework, passed time
- trace와 process-cube 통계
- 객체 중심 통계

개념적으로 이 영역의 일부는 향후 PIX Compute Layer와 가깝다. 그러나 물리적으로 PM4Py 알고리즘은 이러한 통계 함수를 직접 import하고 조합하기도 한다.

### 4.4 `pm4py.visualization`

시각화는 Petri net, BPMN, DFG, process tree, OCEL, transition system, performance spectrum, alignment table 등 process model 또는 결과 type별로 나뉜다.

가장 일반적인 rendering 수단은 Graphviz이며, 다른 경로에서는 Matplotlib과 NetworkX도 사용한다.

### 4.5 `pm4py.streaming`

Streaming 패키지는 online event 처리를 위한 별도의 import, conversion, connector, stream, algorithm을 제공한다. 라이브러리 전체의 구성 중심이라기보다 병렬적인 capability다.

### 4.6 `pm4py.util`

Utility 패키지는 다음을 중앙화한다.

- 환경변수로 제어되는 기본값
- 표준 XES·OCEL parameter key
- 일반 parameter 추출
- algorithm variant 해석
- 날짜와 시간 parsing
- DataFrame utility
- 압축과 low-level helper

---

## 5. 반복되는 알고리즘 구성 패턴

PM4Py의 가장 특징적인 구현 패턴은 다음과 같다.

```text
사용자 대상 함수
    ↓
family-level algorithm.py
    ↓
Variants(Enum)
    ↓
variants/<implementation>.py
    ↓
apply(..., parameters=dict)
```

분석한 트리에는 다음이 있었다.

- `algorithm.py`라는 이름의 파일 106개
- `variants`라는 이름의 디렉터리 164개

일반적인 dispatcher 형태는 다음과 같다.

```python
class Variants(Enum):
    CLASSIC = classic
    ALTERNATIVE = alternative


def apply(data, variant=Variants.CLASSIC, parameters=None):
    return exec_utils.get_variant(variant).apply(data, parameters)
```

`pm4py.util.exec_utils`는 `Enum` key와 raw string key를 모두 지원한다. 이에 따라 typed enumeration과 과거 dictionary 기반 parameter 사용의 호환성을 유지한다.

### 5.1 이 패턴의 장점

- 모든 caller를 바꾸지 않고 새 구현을 추가할 수 있다.
- 한 algorithm family가 여러 backend를 제공할 수 있다.
- caller가 성능 또는 의미론적 variant를 고를 수 있다.
- 구현 모듈이 public facade보다 작게 유지된다.
- 특정 경로를 사용할 때만 선택 의존성을 load할 수 있다.

### 5.2 이 패턴의 구조적 비용

- `apply()`라는 이름만으로 operator 의미를 알 수 없다.
- `parameters: dict`는 정적 검증을 약화한다.
- variant별 option이 일관된 typed contract로 표현되지 않는다.
- algorithm family마다 결과 type이 다르다.
- 결과에 operator identity와 version이 포함되지 않는다.
- unsupported, unavailable, invalid-input 상태가 표준화되어 있지 않다.

이 비용은 PIX 아키텍처에 적합한지를 기준으로 한 관찰이며, PM4Py가 과학 라이브러리로서 잘못 설계됐다는 증거는 아니다.

---

## 6. 대표 실행 경로

### 6.1 XES import

공개 호출은 다음과 같다.

```python
log = pm4py.read_xes("event-log.xes")
```

대략 다음 경로를 따른다.

```text
pm4py.read_xes
→ local path 또는 remote URL 해석
→ parser/backend 선택
→ pm4py.objects.log.importer.xes.importer.apply
→ 선택된 Variants member
→ variants/<parser>.apply
→ EventLog, Pandas DataFrame 또는 선택적 lazy representation
→ 선택적 normalization/conversion
```

검사한 소스가 지원하는 variant에는 다음이 포함된다.

- chunk-regex parsing
- XML iterparse
- XES 2.0 iterparse
- memory-compressed iterparse
- line-by-line parsing
- 선택적 Rust 기반 parsing

공개 API의 기본 방향은 legacy `EventLog` representation에서 벗어나고 있다. `EventLog`, `Trace`, `EventStream`은 DataFrame 중심 사용을 권장하는 runtime deprecation warning을 가진다.

### 6.2 Inductive Miner

Process Tree 경로는 다음과 같다.

```text
DataFrame / EventLog / DFG
→ facade 검증 및 property 추출
→ pm4py.algo.discovery.inductive.algorithm.apply
→ trace를 univariate variant log로 normalize 또는 compress
→ IM, IMf, IMd 선택
→ base-case, cut, fall-through 재귀 처리
→ 생성된 ProcessTree fold 및 sort
→ ProcessTree
```

`discover_petri_net_inductive()`는 Petri-net discovery를 독립적으로 구현하지 않는다. 먼저 Process Tree를 발견한 뒤 initial/final marking을 포함한 Petri net으로 변환한다.

```text
log
→ discover_process_tree_inductive
→ ProcessTree
→ convert_to_petri_net
→ PetriNet + initial marking + final marking
```

이는 PM4Py가 conversion 경로로 capability를 조합하는 사례다.

### 6.3 Alignment conformance

`conformance_diagnostics_alignments()`는 runtime argument 형태에 따라 동작을 선택한다.

```text
PetriNet + markings → Petri-net alignments
DFG + boundaries   → DFG alignments
ProcessTree        → Process-tree alignments
EventLog/DataFrame → edit-distance log-to-log alignments
기타 model          → Petri net 변환 시도 후 align
```

Facade는 multiprocessing 사용 여부와 native list/dictionary diagnostics 또는 DataFrame 반환 여부도 결정한다.

편리한 polymorphic API를 제공하지만, 하나의 정적 return contract만으로 허용 signature와 failure 동작을 모두 이해하기는 어렵다.

### 6.4 Model conversion

Model conversion은 주로 type에 따라 결정된다.

```text
ProcessTree ─┐
BPMN        ─┤
Heuristics  ─┼→ convert_to_petri_net → PetriNet + markings
POWL        ─┤
DFG         ─┘
```

Conversion은 중요한 내부 integration 수단이다. 일부 facade operation은 직접 구현이 없으면 자동 변환을 시도한다.

---

## 7. 데이터와 모델 객체

### 7.1 전통적인 event-log 모델

Legacy object model은 다음과 같다.

```text
Event       # event attribute의 mapping
Trace       # Event sequence와 trace attribute
EventStream # event sequence와 stream/log metadata
EventLog    # Trace collection인 EventStream 파생형
```

이 객체들은 mutable하며 `append`, `insert`, item assignment 같은 list형 변경 operation을 제공한다.

현재 공개 API는 주로 DataFrame을 지향하지만, 기존 알고리즘과 consumer 호환성을 위해 legacy object도 유지한다.

### 7.2 Process-model 객체

PM4Py는 다음 model family에 대한 native object를 정의한다.

- Petri net과 marking
- process tree
- BPMN graph
- directly-follows graph
- heuristics net
- transition system
- trie
- POWL
- stochastic Petri net
- object-centric Petri net
- object-centric causal net

이 객체들은 model-specific conversion, semantics, importer, exporter, analysis, visualization 모듈의 지원을 받는다.

### 7.3 Object-Centric Event Log 모델

PM4Py의 `OCEL` 객체는 여러 Pandas DataFrame을 담는 mutable container다.

```text
OCEL
├── events
├── objects
├── relations          # event-to-object relation
├── o2o                # object-to-object relation
├── e2e                # event-to-event relation
├── object_changes
├── globals
└── parameters
```

객체는 다음에 사용할 column name도 설정 가능하게 보관한다.

- event identifier
- event activity
- event timestamp
- object identifier
- object type
- relation qualifier
- changed field

계산 편의를 위해 `relations` DataFrame은 denormalized되어 있다. Event/object identifier뿐 아니라 event activity, event timestamp, object type을 포함할 수 있다.

### 7.4 OCEL 정합성 처리

검사한 `ocel_consistency.apply()`는 다음을 수행한다.

- identifier, activity, type column을 string으로 변환
- 처리 대상 필수 column에 null이 있는 row 제거
- 해당 column에 empty string이 있는 row 제거
- 중복 event 또는 object identifier warning
- 누락된 relation qualifier를 empty string으로 교체
- `OCEL` 객체의 DataFrame을 변경
- normalization 후 같은 논리적 OCEL container 반환

이 함수는 status, 문제가 있는 relation identifier, evidence reference, assumption을 포함한 structured integrity result를 반환하지 않는다. Filtering propagation utility는 더는 도달할 수 없는 event, object, relation을 관련 DataFrame에서 제거할 수 있다.

따라서 PM4Py consistency 처리는 후속 분석을 위한 operational normalization에 가깝다. PIX가 제안하는 evidence-preserving integrity computation과 동일하지 않다.

---

## 8. 객체 중심 기능의 분포

객체 중심 기능은 독립적인 내부 engine 하나에 모이지 않고 PM4Py 전반에 분포한다.

```text
pm4py/ocel.py
    사용자 대상 OCEL facade

pm4py/objects/ocel/
    OCEL object, import/export, validation, consistency, filtering utility

pm4py/algo/discovery/ocel/
    OC-DFG, OCPN, OTG, ETOT, interleaving 및 관련 discovery

pm4py/algo/conformance/ocel/
    OC-DFG, OTG, ETOT 비교 기반 conformance

pm4py/algo/transformation/ocel/
    Feature extraction, graph conversion, OLAP, splitting

pm4py/statistics/ocel/
    Object graph, event-to-object statistics, interleaving

pm4py/visualization/ocel/
    OC-DFG와 OCPN 시각화
```

### 8.1 OCEL flattening

`ocel_flattening(ocel, object_type)`은 객체 중심 log를 전통적인 case 중심 DataFrame으로 projection한다.

```text
선택된 object type
→ 해당 type의 object가 case identifier가 됨
→ event-object relation이 case와 event를 연결
→ event attribute merge
→ 표준 XES activity, timestamp, case column 생성
```

이 operation은 PIX trace reconstruction과 직접 관련된 projection이다. 동시에 한계를 보여준다. Case 관점으로 object type 하나를 선택해야 하므로 원래의 multi-object context 일부가 손실된다.

### 8.2 OC-DFG discovery

공개 OC-DFG 경로는 다음과 같다.

```text
pm4py.discover_ocdfg
→ column 및 performance parameter 구성
→ pm4py.algo.discovery.ocel.ocdfg.algorithm.apply
→ Variants.CLASSIC
→ variants.classic.apply
→ dictionary result
```

결과 dictionary는 activity, object type, object type별 edge, start activity, end activity와 선택적 performance measurement를 포함한다.

### 8.3 Object summary

최상위 OCEL facade는 다음과 같은 직접적인 Pandas 계산도 수행한다.

- object별 lifecycle activity sequence
- lifecycle 시작·종료 timestamp
- lifecycle duration
- interacting-object graph
- object type별 activity
- event별 관련 object 수

이는 PM4Py가 low-level computation과 사용자 대상 orchestration 사이에 하나의 보편적 경계를 강제하지 않는다는 점을 보여준다.

---

## 9. 의존성 경계

표면적인 의존 방향은 대략 다음과 같다.

```text
facade
   ↓
algo
   ↓
objects / statistics / util
```

실제 import가 엄격하게 단방향인 것은 아니다.

정적 검사에서 다음 사례를 확인했다.

- `objects` 아래 모듈이 `algo`를 import
- 여러 `algo` 모듈이 `statistics`를 import
- 최소 하나의 `algo` 경로가 visualization 동작을 import
- facade 모듈이 conversion과 algorithm 구현을 직접 import
- conformance 함수가 model conversion으로 fallback

따라서 PM4Py는 clean layer 또는 ports-and-adapters 의존 규칙을 강제하는 구조가 아니다. 공통 object type, dictionary, conversion utility, dispatcher convention으로 연결된 feature-oriented package 구조에 가깝다.

이 설명 자체가 비판은 아니다. 범용 과학 라이브러리는 엄격한 아키텍처 격리보다 알고리즘 가용성과 조합 가능성을 우선할 수 있다.

---

## 10. 입력과 결과 계약

### 10.1 입력

PM4Py 알고리즘은 일반적으로 다음 중 하나 이상을 받는다.

- Pandas DataFrame
- legacy `EventLog` 또는 `Trace`
- `OCEL`
- native process-model object
- model과 initial/final state의 tuple
- graph 또는 configuration dictionary
- 선택적 `parameters` dictionary

Column 의미는 대개 다음과 같은 표준 string key로 전달한다.

```text
concept:name
case:concept:name
time:timestamp
ocel:eid
ocel:oid
ocel:type
```

### 10.2 출력

모든 알고리즘이 공유하는 단일 result envelope는 없다. 반환 type에는 다음이 포함된다.

- `pandas.DataFrame`
- `EventLog`
- `OCEL`
- `ProcessTree`
- `PetriNet`과 marking
- dictionary
- dictionary list
- numeric value
- tuple과 set

다음 field는 보편적으로 강제되지 않는다.

- computation identifier
- operator name과 version
- `computed`, `unavailable`, `invalid_input` 같은 명시적 status
- source event와 object identifier
- assumption
- deterministic normalization identity
- evidence reference
- withdrawal condition

이는 제안된 PIX `ComputationResult`, `ProcessFinding` 계약과 실질적으로 다르다.

### 10.3 Failure와 unknown 상태

Failure signaling은 함수마다 다르다. PM4Py는 경로에 따라 다음과 같이 동작할 수 있다.

- generic exception 발생
- warning 출력
- 자동 conversion 시도
- 불일치 row 제거
- empty structure 반환
- algorithm별 schema를 가진 diagnostics dictionary 반환

보편적인 result status가 없으므로 PM4Py의 empty result가 모든 경우에 동일한 의미라고 가정할 수 없다.

---

## 11. 테스트와 예제

### 11.1 확인된 물리 구조

검사한 저장소에는 다음이 있었다.

- Python test 파일 102개
- Python example 파일 206개
- 입력 fixture와 format별 test data
- custom test runner
- coverage 중심 test module
- documentation 및 simplified-interface test

Test는 모든 package path를 그대로 반영하기보다 비교적 평평한 `tests/` 디렉터리에 배치되어 있다.

### 11.2 저장소가 보고한 측정값

2026-07-17자 저장소의 `COVERAGE.md`는 다음을 보고한다.

```text
Tests discovered:       929
Passed:                 926
Skipped:                3
Failed:                 0
Statement coverage:     90.22%
Covered statements:     64,403 / 71,387
```

이는 upstream이 기록한 수치다. 이 구조 분석에서 독립적으로 재현하지 않았다. 따라서 현재 PIX 개발 환경에서의 실제 test result와 coverage는 **알 수 없음**이다.

---

## 12. 아키텍처 특성

### 12.1 확인된 구조적 사실

- PM4Py는 `pm4py/*.py`와 `pm4py/__init__.py`를 통해 광범위한 기능 facade를 제공한다.
- 소스 파일 대부분은 algorithm implementation이다.
- Algorithm family는 `algorithm.py`, `Variants(Enum)`, variant module, `apply()` dispatch를 반복적으로 사용한다.
- 전통적인 event-log operation의 현재 선호 representation은 DataFrame이다.
- Native mutable model object는 process model과 OCEL에서 여전히 중심적이다.
- Conversion 경로로 algorithm과 model representation을 조합한다.
- 객체 중심 기능은 objects, discovery, conformance, transformation, statistics, visualization package에 걸쳐 있다.
- Result shape은 서로 다르며 보편적인 computation contract로 감싸지지 않는다.
- 내부 package 의존성은 엄격한 단방향 layer boundary를 따르지 않는다.

### 12.2 데이터 기반 해석

관찰된 구조는 **과학적 process-mining algorithm을 위한 feature-oriented modular monolith**로 규정하는 것이 가장 정확하다.

이 해석의 근거는 다음과 같다.

1. 하나의 설치 가능한 package가 매우 넓은 기능을 포함한다.
2. Algorithm family는 내부적으로 modularized되어 있다.
3. 공통 object와 converter가 이 모듈들을 연결한다.
4. Facade 함수가 여러 구현 사이를 동적으로 routing한다.
5. Package boundary가 엄격한 의존 방향을 강제하지 않는다.
6. 독립적인 compute-result 또는 intelligence-result protocol이 시스템을 통제하지 않는다.

후속 전체 dependency 분석에서 현재 검사 경로로 보이지 않은 강제 경계 또는 runtime plugin contract가 확인되면 이 해석을 철회해야 한다.

---

## 13. PIX 계승에 대한 예비 시사점

### 13.1 참조할 가치가 있는 패턴

1. **Public facade와 구현 package의 분리**
   Consumer가 내부 algorithm 위치를 알 필요가 없다.

2. **Algorithm-family 구성**
   관련 구현이 안정된 의미 단위 아래 모인다.

3. **교체 가능한 variant**
   하나의 개념적 operation 뒤에 여러 구현을 둘 수 있다.

4. **명시적인 converter와 projection**
   모든 algorithm에 모든 representation을 내장하지 않고 process representation을 변환할 수 있다.

5. **DataFrame 중심 계산 경로**
   안정된 contract 뒤에 둘 경우 tabular computation은 효율적이고 상호 운용 가능하다.

6. **광범위한 fixture와 example coverage**
   Algorithm에 실제 파일, negative path, format test, 실행 가능한 example이 함께 제공된다.

### 13.2 현재 PIX 기준선과 충돌하는 패턴

1. **Mutable canonical OCEL container**
   PIX에는 예측 가능한 neutral contract와 재현 가능한 computation input이 필요하다.

2. **주요 operator contract로 쓰이는 untyped `parameters` dictionary**
   PIX operator에는 명시적 semantics, assumption, versioning이 필요하다.

3. **서로 다른 unwrapped result**
   PIX에는 computation status, source reference, unavailable-state 보존이 필요하다.

4. **Invalid row를 제거하는 자동 normalization**
   PIX는 integrity defect를 조용히 사라지게 하지 않고 보존·보고해야 한다.

5. **암묵적 conversion과 fallback**
   PIX는 semantic projection과 assumption을 가시화해야 한다.

6. **강제 경계 없는 compute와 interpretation**
   PIX Compute Layer는 Intelligence Layer와 독립적으로 test할 수 있어야 한다.

7. **광범위한 기능 확장**
   PM4Py의 discovery, visualization, machine learning, 범용 mining 범위는 PIX v0.1을 넘어선다.

8. **라이선스 결정 전 직접적인 소스 계승**
   아키텍처 학습만으로 코드 재사용의 법적 호환성이 성립하지 않는다.

### 13.3 예비 adaptation mapping

| PM4Py 개념 | 가능한 PIX 해석 | PIX에서 필요한 강화 |
| --- | --- | --- |
| facade function | 공개 PIX operator/API | `compute → interpret → project` 보존 |
| `algorithm.py` | operator dispatcher | 명시적인 operator identity와 version |
| `Variants(Enum)` | operator 구현 선택 | typed configuration과 deterministic selection |
| `parameters: dict` | operator configuration | open dictionary가 아닌 validated contract |
| DataFrame/EventLog/OCEL | 입력 representation | neutral `ProcessDataset`으로 normalize |
| algorithm return value | computation output | `ComputationResult`로 wrapping |
| diagnostics dictionary | process finding 입력 | evidence-linked `ProcessFinding` |
| OCEL flattening | object projection | projection assumption과 손실 context 보존 |
| OCEL consistency utility | relation-integrity computation | invalid reference를 조용히 repair하지 않고 보고 |
| conversion fallback | 명시적 projection/conversion | conversion path와 semantic assumption 기록 |

이 mapping은 예비 판단이다. 아키텍처 관계를 식별할 뿐 승인된 구현 결정을 뜻하지 않는다.

---

## 14. 후속 분석이 필요한 미확인 사항

완료한 구조 검사만으로는 다음을 확정할 수 없다.

- 대표 PM4Py operator의 runtime performance
- Schumpeter 규모 OCEL data에서의 memory behavior
- 모든 operator의 deterministic behavior
- thread 및 multiprocessing reproducibility
- algorithm variant 사이의 정확한 의미 차이
- PM4Py release 간 내부 API 안정성
- 모든 import format에서 malformed 또는 dangling OCEL relation 처리
- PM4Py OCEL projection이 Schumpeter mission data에 적합한지
- 특정 algorithm의 PIX v0.1 실제 재사용 가치
- AGPL PM4Py 소스 재사용과 향후 PIX license의 법적 호환성
- 독립적으로 검증한 현재 test pass rate와 coverage

이 수치와 판단은 targeted analysis 또는 experiment 전까지 **알 수 없음**이다.

---

## 15. 유효기간과 철회 조건

### 15.1 유효기간

이 분석은 다음 PM4Py commit에 유효하다.

```text
3329bbcbadce8764f7df660fd88636c30793fbd0
```

비교 없이 이후 upstream release도 동일하다고 가정해서는 안 된다.

### 15.2 철회 조건

다음 경우 관련 판단을 재검토하거나 철회한다.

- PM4Py의 주요 package layout이 바뀐 경우
- facade와 algorithm dispatch mechanism이 교체된 경우
- 일관된 typed computation-result contract가 도입된 경우
- OCEL이 immutable이 되거나 evidence-preserving integrity result를 제공하는 경우
- dependency enforcement가 이 검사에서 보이지 않은 엄격한 경계를 드러내는 경우
- runtime execution이 추적한 call path와 다른 경우
- PIX가 좁은 audit engine에서 범용 process-mining suite로 확장되는 경우
- PIX의 라이선스와 배포 모델상 PM4Py 직접 통합의 호환 또는 비호환이 명확해진 경우
- 더 깊은 algorithm-level 분석이 현재의 예비 adaptation 판단을 반증하는 경우

---

## 16. 최종 평가

**PM4Py는 `public facade → algorithm dispatcher → variant implementation`을 주요 확장 패턴으로 사용하는 광범위한 feature-oriented modular monolith다. Algorithm 구성, conversion mechanism, 객체 중심 처리는 PIX에 유용한 참조지만, mutable data container, open parameter dictionary, 이질적인 result, 암묵적 normalization, 엄격하지 않은 dependency boundary는 상당한 재설계 없이 PIX가 제안하는 evidence-first computation 및 intelligence contract를 충족하지 못한다.**
