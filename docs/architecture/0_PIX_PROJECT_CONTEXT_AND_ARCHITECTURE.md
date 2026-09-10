<!-- 한국어 버전 -->

# PIX 프로젝트 컨텍스트 및 아키텍처

**문서 유형:** 정본 프로젝트 컨텍스트 / 아키텍처 기준선 / 개발 인계  
**프로젝트:** PIX  
**버전:** 컨텍스트 기준선 v0.1  
**날짜:** 2026-07-18  
**상태:** 프로젝트 초기화를 위한 정본 기준선 제안

---

## 0. 목적

이 문서에서는 새로운 PIX 프로젝트 대화, Vera, Codex에 대한 이해의 충분한 맥락을 제공합니다.

1. 왜 PIX이 만들어지고 있는지;
2. 어떤 문제를 해결해야 하는지,
3. PIX과 Schumpeter의 차이점
4. 이전 OCPX 및 PIG 개념을 통합하는 방법
5. 가장 먼저 실행해야 할 사항
6. 적용 범위를 벗어나야 하는 것
7. 개발과 검증이 어떻게 진행되어야 하는가.

이것은 PIX이 이미 완성된 시스템으로 존재한다는 주장이 아닙니다. 그것은 작은 테스트 가능한 Process Intelligence 엔진으로 PIX을 만드는 초기 아키텍처 계약입니다.

---

## 1. 명칭 및 계보 프로젝트

### 1.1 정본 이름

새로운 아키텍처는 다음과 같은 활성 프로젝트 이름만을 사용합니다:

- **Schumpeter** — PI-native 에이전트 런타임 및 미션 제어 평면.
- **PIX** — 독립적인 Process Intelligence 계산 및 해석 엔진

접두사 **Chanta** 는 새로운 PIX 패키지 이름, 모듈 이름, 저장소 이름, 사용자 대상 문서 또는 API에 사용할 수 없습니다.

추천된 이름:

```text
Repository: PIX
Python package: pix
Import namespace: pix
```

ChantaCore, ChantaGrowthKernel, OCPX 및 PIG와 같은 역사적 이름은 마이그레이션 노트 또는 아키텍처-계보 문서에서만 나타날 수 있습니다.

### 1.2 PIX으로 통합된 역사적 개념

이전 아키텍처는 다음과 같이 구별되었습니다.

- **OCPX** — 객체 중심 프로세스 계산
- **PIG** — 프로세스 해석, 진단, 준수 및 가이드.

PIX은 둘 다 하나의 프로젝트로 통합합니다.

```text
PIX
├── Compute Layer         # former OCPX responsibility
├── Intelligence Layer    # former PIG responsibility
└── Projection Layer      # process-state projection for consumers
```

그들은 물리적으로 통합하지만 논리적으로 분리되어 있습니다.

---

## 2. 문제 진술

이전 시스템은 이벤트, 객체, 관계, 추적, 검증 및 증거 유물을 축적했지만, 그 감사 능력은 종종 존재 검증 수준에서 유지되었습니다.

```text
Does an event exist?
Does a row exist?
Is a flag true?
Was a test command recorded?
```

이러한 검사는 다음을 증명하지 않습니다:

- 필요한 사건은 올바른 순서로 발생했습니다.
- 그 결과물이 검증한다고 주장하는 유물과 연결되어 있습니다.
- 임무는 필요한 모든 기준을 충족시킵니다.
- 전략 변경 또는 반복적인 실패로 재시행
- 완료 주장은 충분한 증거로 뒷받침된다.

부족한 기능은 OCEL 원장과 에이전트의 임무 결정 사이의 결정적 계산 및 해석 층입니다.

PIX은 그 격차를 채우기 위해 존재합니다.

---

## 3. 시스템 위치

### 3.1 높은 수준의 흐름

```text
Schumpeter Runtime
    ↓
OCEL event / object / relation data
    ↓
Schumpeter PIX Adapter
    ↓
PIX ProcessDataset
    ↓
PIX Compute
    ↓
PIX Intelligence
    ↓
PIX Process-State Projection
    ↓
Schumpeter Mission Auditor
    ↓
Complete / Retry / Request Evidence / Escalate / Fail
```

### 3.2 핵심 책임 분할

#### Schumpeter의 소유자

- 사용자 및 임무 입력;
- 임무 및 기준 정의
- 에이전트 루프 및 리네스 실행;
- 제공자, 도구, 허가 및 작업 공간 운영;
- OCEL 배출량 및 지속성
- Schumpeter에 특화된 규칙 프로파일
- 최종 임무 결정
- 실제 재시행, 격상, 중단, 종료.

#### PIX의 소유자

- 중립적인 프로세스 데이터 계약
- 객체 중심의 프로젝션
- 발자국 재구성
- 구조 및 시간 계산
- 증거계보 계산
- 공정 연구결과
- 프로세스 상태 예측
- 결정적 진단과 권고

### 3.3 의존성 방향

의존성은 일방적으로 유지되어야 합니다.

```text
Schumpeter → PIX
PIX ─X→ Schumpeter
```

PIX은 결코 Schumpeter 클래스, 미션 모델, 런타임 서비스, 데이터베이스 소유자, 공급자 또는 도구를 수입해서는 안 됩니다.

---

## 4. 물리적 저장소 구조

PIX은 Git의 형제 프로젝트가어야 하며, Schumpeter 내부의 하위 디렉토리가 아니어야 합니다.

권장 작업 공간:

```text
D:\
├── Schumpeter\
├── PIX\
└── ChantaCore\        # frozen historical reference only
```

초기 개발 중에, Schumpeter은 편집 가능한 로컬 의존성으로 PIX을 섭취할 수 있습니다.

```bash
pip install -e D:\PIX
```

초기에는 Git 하위 모듈을 사용하지 마십시오. 형제자매 저장소 및 편집 가능한 의존성은 불필요한 저장소 관리 전반적인 비용을 지불하지 않고 독립적인 역사와 테스트를 제공합니다.

---

## 5. 추천된 PIX 저장소 레이아웃

```text
PIX/
├── pyproject.toml
├── README.md
├── LICENSE
├── docs/
│   ├── PIX_PROJECT_CONTEXT_AND_ARCHITECTURE.md
│   ├── ARCHITECTURE.md
│   ├── CONTRACTS.md
│   └── OPERATOR_CATALOG.md
│
├── src/
│   └── pix/
│       ├── __init__.py
│       │
│       ├── contracts/
│       │   ├── __init__.py
│       │   ├── event.py
│       │   ├── object.py
│       │   ├── relation.py
│       │   ├── dataset.py
│       │   ├── constraint.py
│       │   └── result.py
│       │
│       ├── compute/
│       │   ├── __init__.py
│       │   ├── projection.py
│       │   ├── trace.py
│       │   ├── integrity.py
│       │   ├── temporal.py
│       │   ├── lifecycle.py
│       │   ├── lineage.py
│       │   └── recovery.py
│       │
│       ├── intelligence/
│       │   ├── __init__.py
│       │   ├── rules.py
│       │   ├── conformance.py
│       │   ├── diagnostics.py
│       │   ├── findings.py
│       │   └── recommendations.py
│       │
│       ├── projection/
│       │   ├── __init__.py
│       │   ├── process_state.py
│       │   └── context_projection.py
│       │
│       ├── engine.py
│       └── api.py
│
└── tests/
    ├── fixtures/
    ├── contracts/
    ├── compute/
    ├── intelligence/
    └── integration/
```

패키지는 이 레이아웃보다 작게 시작될 수 있습니다. 공허한 점유지 모듈은 단지 프로젝트가 완성된 것처럼 보일 수 있도록 만들어서는 안 됩니다.

---

## 6. 내부 층의 경계

### 6.1 계산 계층

계산 계층은 결정적 과정 사실을 생성합니다.

그것은 이렇게 대답할 수 있습니다.

- 어떤 사건들이 객체와 관련이 있는지;
- 관찰된 흔적이 무엇인지
- 관계들이 구조적으로 유효한지,
- 라이프사이클 활동이 없는지,
- 시간적 제약이 침해되었는지,
- 주장의 증거 경로가 있는지 여부는
- 얼마나 많은 재시험이 있었는지
- 다시 시도하는 동안 전략이 바뀌었는지

미션 정책에 관한 결정을 내리지 않아야 합니다.

예를 들어:

```python
result = check_temporal_constraints(
    trace=trace,
    constraints=[
        Before("provider_call_started", "provider_call_completed"),
        Before("provider_call_completed", "assistant_response_recorded"),
    ],
)
```

### 6.2 지능층

정보 계층은 계산 결과를 해석합니다.

이것은 다음과 같은 결과를 초래할 수 있습니다.

- 실종된 라이프사이클 연구결과
- 시간 순서를 위반한 사실이 밝혀진 것
- 고아자증의 결과
- 모호한 출처 조사결과
- 거짓으로 완료되는 위험의 성과
- 비효율적인 재검토 결과;
- 제한된 권고사항

모든 발견은 하나 이상의 계산 결과를 참조해야 합니다.

### 6.3 투명층

프로젝션 레이어는 Schumpeter 또는 다른 클라이언트가 사용할 수 있는 프로세스 상태 시각으로 계산 및 출력을 찾는 것을 압축합니다.

예제 투명:

```text
Current process state:
- observed lifecycle stage: verification
- completed required activities: 5 / 6
- missing required activity: regression_test_completed
- temporal violations: 1
- unresolved evidence claims: 2
- recommended next action: request regression-test evidence
```

### 6.4 수입 경계

PIX 내부에서 필요한 방향:

```text
contracts
   ↑
compute
   ↑
intelligence
   ↑
projection / engine / api
```

규칙:

- `compute`은 `intelligence`을 수입할 수 없습니다.
- `intelligence`은 컴퓨팅 결과 계약을 사용할 수 있습니다.
- `projection`은 둘 다 섭취할 수 있습니다.
- 어떤 모듈도 Schumpeter을 수입할 수 없습니다.

---

## 7. 중립적인 데이터 계약

PIX은 Schumpeter의 데이터베이스를 직접 읽을 수 없습니다. Schumpeter은 OCEL의 지속성을 중립적인 PIX 계약으로 전환합니다.

초기 계약 형태:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

@dataclass(frozen=True)
class ProcessEvent:
    event_id: str
    activity: str
    timestamp: datetime
    attributes: Mapping[str, object]

@dataclass(frozen=True)
class ProcessObject:
    object_id: str
    object_type: str
    attributes: Mapping[str, object]

@dataclass(frozen=True)
class EventObjectRelation:
    event_id: str
    object_id: str
    qualifier: str | None

@dataclass(frozen=True)
class ObjectObjectRelation:
    source_object_id: str
    target_object_id: str
    qualifier: str | None

@dataclass(frozen=True)
class ProcessDataset:
    events: tuple[ProcessEvent, ...]
    objects: tuple[ProcessObject, ...]
    event_object_relations: tuple[EventObjectRelation, ...]
    object_object_relations: tuple[ObjectObjectRelation, ...]
```

계약은 진화할 수 있지만 변경은 명시적이고 버전이 있어야 합니다.

---

## 8. 계산 및 발견 계약

### 8.1 계산 결과

```python
@dataclass(frozen=True)
class ComputationResult:
    computation_id: str
    operator_name: str
    operator_version: str
    status: str
    value: object
    source_event_ids: tuple[str, ...]
    source_object_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
```

추천된 상태:

```text
computed
unavailable
invalid_input
```

실패하거나 사용할 수 없는 계산은 조용히 `False`, 0 또는 빈 목록이 될 수 없습니다.

### 8.2 프로세스 발굴

```python
@dataclass(frozen=True)
class ProcessFinding:
    finding_id: str
    rule_id: str
    finding_type: str
    severity: str
    statement: str
    computation_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    recommended_action: str | None
    withdrawal_condition: str | None
```

모든 발견은 그 컴퓨팅 기반을 인용해야 합니다.

### 8.3 통합 분석 결과

```python
@dataclass(frozen=True)
class PIXAnalysisResult:
    computations: tuple[ComputationResult, ...]
    findings: tuple[ProcessFinding, ...]
    process_state: object | None
    unavailable_computations: tuple[str, ...]
```

---

## 9. 초기 사업자 카탈로그

PIX v0.1은 실제 Schumpeter 감사에 필요한 사업자만 구현해야 합니다.

### 9.1 초기 사업자 요구

1. `project_events_by_object`
2. `reconstruct_trace`
3. `check_relation_integrity`
4. `check_temporal_constraints`
5. `compute_lifecycle_completeness`
6. `compute_evidence_lineage`
7. `compute_retry_recovery_metrics`

### 9.2 초기 발견

1. `missing_lifecycle_activity`
2. `temporal_order_violation`
3. `dangling_relation`
4. `orphan_evidence`
5. `ambiguous_provenance`
6. `false_completion_risk`
7. `ineffective_retry`

### 9.3 v0.1에서 명시적으로 제외

- 자동 프로세스 탐지
- 페트리 네트워크 발견
- 전체 객체 중심의 적합성 검사는
- 예측 모니터링
- 인과적 추론
- 기계 학습 기질의 탐지
- 자동 정책 변동
- 자동 기술 학습
- LLM 기반의 판단
- 일반 산업 프로세스 온톨로지
- 원격 서비스 또는 데몬 모드
- 그래프 데이터베이스 의존성

---

## 10. 공공 API

PIX은 명시적이고 통합된 API을 노출시켜야 한다.

### 10.1 명백한 파이프라인

```python
computations = pix.compute(
    dataset=dataset,
    operators=[
        "relation_integrity",
        "trace_reconstruction",
        "temporal_conformance",
        "evidence_lineage",
    ],
)

findings = pix.interpret(
    computations=computations,
    rule_set=rule_set,
)

projection = pix.project(
    computations=computations,
    findings=findings,
)
```

### 10.2 통합 파이프라인

```python
analysis = pix.analyze(
    dataset=dataset,
    rule_set=rule_set,
)
```

통합된 API은 내부적으로:

```text
compute → interpret → project
```

---

## 11. Schumpeter 통합 계약

Schumpeter은 어댑터 및 도메인별 규칙 프로파일만 포함해야 합니다.

권장되는 Schumpeter 사이드:

```text
Schumpeter/
└── src/
    └── schumpeter/
        └── integrations/
            └── pix/
                ├── dataset_adapter.py
                ├── rule_profile.py
                ├── result_mapper.py
                └── service.py
```

책임:

- `dataset_adapter.py`
  - Schumpeter OCEL 데이터를 `ProcessDataset`로 변환합니다.
- `rule_profile.py`
  - Schumpeter에 특화된 라이프 사이클 및 증거 규칙을 정의합니다.
- `result_mapper.py`
  - PIX 분석이 Schumpeter 감사 입력에 대한 지도;
- `service.py`
  - 호출 경계를 제어합니다.

PIX은 Schumpeter 임무의 완료 여부를 결정할 수 없습니다. 그것은 과정의 사실과 결과를 제공합니다. Schumpeter은 미션 정책을 적용합니다.

정본 경계:

```text
PIX = process facts, computations, findings
Schumpeter = mission policy and action decision
```

---

## 12. 첫 번째 수직 조각

첫 번째 수직 조각은 PIX이 실제 감사 결정을 개선한다는 것을 증명해야 합니다.

추천된 후보자:

### 지원자 A — 공급업체의 생애주기 감사

예상 순서:

```text
provider_call_started
→ provider_call_completed
→ assistant_response_recorded
→ route_decision_recorded
```

필요한 경우:

- 완전히 일치하는 흔적;
- 모든 사건들이 존재하지만 순서가 잘못되어 있습니다.
- 공급업체의 완료가 없어지는 경우
- 공급자의 정체성이 모호하다.
- 제공자의 출처 없이 기록된 응답

### 지원자 B — 시험 실패 임무 감사

필요한 과정:

```text
mission_started
→ failure_reproduced
→ code_changed
→ target_test_completed
→ regression_test_completed
→ verification_completed
→ mission_completed
```

필요한 경우:

- 완전한 증거와 완성;
- 목표 테스트가 통과하지만 회귀 테스트가 없습니다.
- 테스트 결과 텍스트는 테스트 실행 계보 없이 존재합니다.
- 허용된 범위를 벗어나 코드 변경
- 전략 변경 없이 반복해서 시도합니다.

우선 한 명의 후보만 실행되어야 합니다. 둘 다 동시에 시작하지 마십시오.

---

## 13. 개발 원칙

### 13.1 수직 절단 규칙

특징은 단지 모델이나 스키마가 있기 때문에 완전하지 않습니다.

완전한 특징은 다음을 포함해야 합니다.

```text
input fixture
→ computation
→ finding
→ public API result
→ tests
→ consumer-facing example
```

### 13.2 증거 우선 규칙

- 모든 발견 참조 계산;
- 모든 계산은 소스 이벤트나 객체를 참조합니다.
- 가설이 명백하다.
- `UNKNOWN`과 `unavailable`은 1급 국가입니다.

### 13.3 결정주의 규칙

동일한 정상화된 입력과 운영체 버전은 동일한 출력을 생성해야 합니다.

### 13.4 지원되지 않은 복합 점수가 없습니다

예측 유효성이 경험적으로 입증될 때까지 단일 — PI 스코어, — Audit 스코어, — 또는 — Agent Intelligence 스코어를 만들지 마십시오.

분해된 출력을 선호합니다.

```text
trace completeness: fail
temporal conformance: fail
relation integrity: pass
required evidence coverage: 3 / 5
recovery effectiveness: unavailable
```

### 13.5 예측 가능한 프레임워크 성장률이 없습니다

새로운 사업자는 다음 각 호의 경우에만 추가될 수 있습니다

- 실제 감사 문제가 이를 요구합니다.
- 합격 시험이 작성될 수 있습니다.
- 그 결과는 실제 결정을 변경하거나 명확히 합니다.

---

## 14. 시험 전략

### 14.1 단위 시험

각 사업자는 긍정적, 부정적, 잘못된 입력 및 사용할 수 없는 입력 테스트를 수행해야 합니다.

### 14.2 계약 시험

시험해보세요.

- 변함없는 계약은 예측할 수 있는 행동을 취한다.
- 시간표가 정상화됩니다.
- 알려지지 않은 참조가 거부되거나 보고됩니다.
- 비효율적 인 관계는 침묵으로 사라지지 않습니다.

### 14.3 통합 테스트

전체 흐름을 테스트:

```text
ProcessDataset
→ PIX compute
→ PIX intelligence
→ process-state projection
```

### 14.4 Schumpeter 통합 테스트

이들은 Schumpeter에 속해 PIX이 아닌:

```text
Schumpeter OCEL fixture
→ Schumpeter adapter
→ PIX
→ Schumpeter mission-audit decision
```

---

## 15. 위험 레지스터

### 리스크 1 — PIX은 Schumpeter 트레이스 유틸리티가 됩니다

제어:

- Schumpeter의 수입이 없습니다.
- 중립 계약만
- 운영자에서 하드코딩된 제공자나 임무 이름이 없습니다.

### 리스크 2 — 컴퓨팅과 지능이 얽혀있다

제어:

- 일방적인 내부 수입
- 독립적으로 테스트 할 수 있는 계산 결과
- 모든 발견은 계산 ID를 참조합니다

### 리스크 3 — PIX은 큰 규모의 연구 플랫폼이 됩니다

제어:

- 실제 수직 절단 필요 없이 운영자가 없습니다.
- 상상 가능한 미래의 용량을 위한 빈 모듈이 없습니다.
- v0.1에서 프로세스 발견이나 ML 작업이 없습니다.

### 리스크 4 — 어댑터는 실제 정보 계층이 됩니다

제어:

- 어댑터는 번역만을 수행합니다.
- 도메인 규칙은 여전히 선언적일 것입니다.
- 계산은 PIX 안에 남아 있습니다.
- 마지막 임무 정책은 Schumpeter 내부에 남아 있습니다.

### 위험 5 — 잘못된 프로세스 의미학은 잘못된 신뢰를 낳습니다

제어:

- 가설이 명백하다.
- 알려지지 않은 상태와 사용할 수 없는 상태는 여전히 눈에 띄게 남아 있습니다.
- 반사 예시 장치는 필수적입니다.
- 순서관 상관관계를 통해서 인과관계에 대한 주장이 없습니다.

---

## 16. 결정 분류

### 확인된 사실

- 전용 OCPX 또는 PIG 구현은 현재 존재하지 않습니다.
- 이전 아키텍처는 이벤트, 객체, 관계, 흔적 및 OCEL 기반을 포함했습니다.
- 부족한 능력은 결정적인 프로세스 컴퓨팅과 증거에 대한 인식한 해석입니다.
- PIX은 Schumpeter과 독립하여 첫 번째 소비자 역할을 하는 것을 목적으로 한다.

### 데이터 기반 해석

- OCPX와 PIG를 하나의 PIX 프로젝트로 통합하는 것은 프로젝트 및 계약 전반적인 비용을 조기 줄이는 것입니다.
- 내부 계층으로 계산과 지능을 유지하는 것은 테스트 가능성과 미래의 추출 옵션을 보존합니다.
- 형제 저장소는 PIX에 Schumpeter을 삽입하는 것보다 더 적합하다.

### 높은 확률 가설

- PIX의 첫 번째 측정 가능한 가치는 고급 프로세스 발견보다는 시간적 위반, 증거 공백 및 잘못된 완료를 탐지하는 것으로 나타납니다.

### 불확실성 / 검증이 필요합니다

- PIX이 미션 성공을 향상시키거나 잘못된 완성을 줄이는 정도는 아직 측정되지 않았습니다.
- Schumpeter 이외의 재사용은 가정보다 입증되어야 합니다.

---

## 17. 철회 및 재평가 조건

아키텍처를 재고하는 경우:

- 대부분의 사업자는 Schumpeter 내부에 대한 직접적인 지식이 필요합니다.
- 어댑터 코드는 컴퓨팅 엔진보다 커집니다.
- 패키지 분리은 첫 번째 수직 조각을 실질적으로 차단합니다.
- 컴퓨팅과 지능은 호환되지 않는 방출 주기를 요구합니다.
- PIX은 직접적인 제약이나 SQL 쿼리에 대해 측정 가능한 감사 값을 추가하지 않습니다.
- 결과는 결정적으로 복제될 수 없습니다.
- 연구결과는 일반적으로 계산 증거가 부족합니다.

이 아키텍처를 다음으로 검토하십시오.

- 첫 번째 6 — 7 사업자가 구현됩니다.
- 한 개의 수직 조각이 완료됩니다.
- 20~30 대표적인 임무 감사가 평가된다.

---

## 18. PIX v0.1 출국 기준

PIX v0.1는 다음과 같은 경우에만 완전합니다.

- 저장소 및 패키지는 `PIX` 및 `pix`로 지정되어 있습니다.
- 중립 계약이 존재하고 시험되고 있습니다.
- 적어도 하나의 객체 투영 작업;
- 추적 재건 작업;
- 관계 무결성이 계산됩니다.
- 시간적 제약이 계산됩니다.
- 라이프사이클의 완전성을 계산한다.
- 증거 계보가 계산됩니다.
- 최소 4개의 성과가 계산에서 발생한다.
- 모든 발견 참조 계산;
- 통합된 `analyze()` API 공장
- 한 개의 수직 조각이 표시됩니다.
- 문서와 사업자 카탈로그가 존재합니다.
- 모든 집중 및 회귀 테스트가 통과됩니다.
- PIX은 Schumpeter의 수입을 포함하지 않습니다.

---

## 19. 출처 계보

이 기준선에서는 다음과 같이 이전에 논의된 개념을 통합합니다.

- `process_intelligence_digital_twin_concept.md`
- `chanta_research_group_schumpeter_bridge_guide.md`
- `ChantaGrowthKernel_ProcessIntelligence_Architecture.md`
- `schumpeter_docs_v3.9_to_v4.0.md`
- `Schumpeter-Architecture-Specification-(for-ChantaGrowthKernel).txt`
- `ChantaCore Codex Prompt Generation Standard.pdf`

이 문서들은 역사적인 설계 자료입니다. 이 문서는 나중에 명시적인 PIX 아키텍처 결정으로 대체되지 않는 한 새로운 PIX 프로젝트의 정본 시작 배경입니다.

---

## 20. 최종 정의

**PIX은 독립적이고 결정적인 Process Intelligence 계산 및 해석 엔진으로 객체 중심의 이벤트 데이터를 재생 가능한 프로세스 사실, 증거에 연결된 연구결과 및 컴팩트 된 프로세스 상태 예측으로 변환합니다. Schumpeter은 미션 정책 및 행동 결정에 계속 책임이 있습니다.**

---

<!-- English version -->

# PIX Project Context and Architecture

**Document type:** Canonical project context / architecture baseline / development handoff  
**Project:** PIX  
**Version:** Context Baseline v0.1  
**Date:** 2026-07-18  
**Status:** Proposed canonical baseline for project initialization

---

## 0. Purpose

This document gives a new PIX project conversation, Vera, and Codex enough context to understand:

1. why PIX is being created;
2. what problem it must solve;
3. how PIX differs from Schumpeter;
4. how the former OCPX and PIG concepts are consolidated;
5. what must be implemented first;
6. what must remain out of scope;
7. how development and verification must proceed.

This is not a claim that PIX already exists as a completed system. It is the starting architectural contract for creating PIX as a small, testable Process Intelligence engine.

---

## 1. Naming and Project Lineage

### 1.1 Canonical names

The new architecture uses only these active project names:

- **Schumpeter** — the PI-native agent runtime and mission control plane.
- **PIX** — the independent Process Intelligence computation and interpretation engine.

The prefix **Chanta** must not be used in new PIX package names, module names, repository names, user-facing documentation, or APIs.

Recommended names:

```text
Repository: PIX
Python package: pix
Import namespace: pix
```

Historical names such as ChantaCore, ChantaGrowthKernel, OCPX, and PIG may appear only in migration notes or architecture-lineage documents.

### 1.2 Historical concepts consolidated into PIX

The earlier architecture distinguished:

- **OCPX** — object-centric process computation;
- **PIG** — process interpretation, diagnostics, conformance, and guidance.

PIX consolidates both into one project:

```text
PIX
├── Compute Layer         # former OCPX responsibility
├── Intelligence Layer    # former PIG responsibility
└── Projection Layer      # process-state projection for consumers
```

They are physically unified but logically separated.

---

## 2. Problem Statement

The previous system accumulated event, object, relation, trace, verification, and evidence artifacts, but its audit capability often remained at the level of existence checks:

```text
Does an event exist?
Does a row exist?
Is a flag true?
Was a test command recorded?
```

These checks do not prove that:

- required events occurred in the correct order;
- an outcome is linked to the artifact it claims to verify;
- a mission satisfies all required criteria;
- a retry changed strategy or merely repeated failure;
- a completion claim is supported by sufficient evidence.

The missing capability is a deterministic computation and interpretation layer between the OCEL ledger and the agent's mission decision.

PIX exists to fill that gap.

---

## 3. System Position

### 3.1 High-level flow

```text
Schumpeter Runtime
    ↓
OCEL event / object / relation data
    ↓
Schumpeter PIX Adapter
    ↓
PIX ProcessDataset
    ↓
PIX Compute
    ↓
PIX Intelligence
    ↓
PIX Process-State Projection
    ↓
Schumpeter Mission Auditor
    ↓
Complete / Retry / Request Evidence / Escalate / Fail
```

### 3.2 Core responsibility split

#### Schumpeter owns

- user and mission intake;
- mission and criterion definitions;
- agent loop and harness execution;
- provider, tool, permission, and workspace operations;
- OCEL emission and persistence;
- Schumpeter-specific rule profiles;
- final mission decisions;
- actual retries, escalation, interruption, and termination.

#### PIX owns

- neutral process-data contracts;
- object-centric projections;
- trace reconstruction;
- structural and temporal computation;
- evidence-lineage computation;
- process findings;
- process-state projection;
- deterministic diagnostics and recommendations.

### 3.3 Dependency direction

The dependency must remain one-way:

```text
Schumpeter → PIX
PIX ─X→ Schumpeter
```

PIX must never import Schumpeter classes, mission models, runtime services, database owners, providers, or tools.

---

## 4. Physical Repository Structure

PIX should be a sibling Git project, not a subdirectory inside Schumpeter.

Recommended workspace:

```text
D:\
├── Schumpeter\
├── PIX\
└── ChantaCore\        # frozen historical reference only
```

During early development, Schumpeter may consume PIX through an editable local dependency:

```bash
pip install -e D:\PIX
```

Do not use a Git submodule initially. A sibling repository plus editable dependency provides independent history and tests without unnecessary repository-management overhead.

---

## 5. Recommended PIX Repository Layout

```text
PIX/
├── pyproject.toml
├── README.md
├── LICENSE
├── docs/
│   ├── PIX_PROJECT_CONTEXT_AND_ARCHITECTURE.md
│   ├── ARCHITECTURE.md
│   ├── CONTRACTS.md
│   └── OPERATOR_CATALOG.md
│
├── src/
│   └── pix/
│       ├── __init__.py
│       │
│       ├── contracts/
│       │   ├── __init__.py
│       │   ├── event.py
│       │   ├── object.py
│       │   ├── relation.py
│       │   ├── dataset.py
│       │   ├── constraint.py
│       │   └── result.py
│       │
│       ├── compute/
│       │   ├── __init__.py
│       │   ├── projection.py
│       │   ├── trace.py
│       │   ├── integrity.py
│       │   ├── temporal.py
│       │   ├── lifecycle.py
│       │   ├── lineage.py
│       │   └── recovery.py
│       │
│       ├── intelligence/
│       │   ├── __init__.py
│       │   ├── rules.py
│       │   ├── conformance.py
│       │   ├── diagnostics.py
│       │   ├── findings.py
│       │   └── recommendations.py
│       │
│       ├── projection/
│       │   ├── __init__.py
│       │   ├── process_state.py
│       │   └── context_projection.py
│       │
│       ├── engine.py
│       └── api.py
│
└── tests/
    ├── fixtures/
    ├── contracts/
    ├── compute/
    ├── intelligence/
    └── integration/
```

The package may begin smaller than this layout. Empty placeholder modules must not be created merely to make the project look complete.

---

## 6. Internal Layer Boundaries

### 6.1 Compute Layer

The Compute Layer produces deterministic process facts.

It may answer:

- which events are related to an object;
- what the observed trace is;
- whether relations are structurally valid;
- whether lifecycle activities are missing;
- whether temporal constraints are violated;
- whether a claim has an evidence path;
- how many retries occurred;
- whether strategy changed between retries.

It must not produce mission-policy decisions.

Example:

```python
result = check_temporal_constraints(
    trace=trace,
    constraints=[
        Before("provider_call_started", "provider_call_completed"),
        Before("provider_call_completed", "assistant_response_recorded"),
    ],
)
```

### 6.2 Intelligence Layer

The Intelligence Layer interprets computation results.

It may produce:

- missing-lifecycle findings;
- temporal-order violation findings;
- orphan-evidence findings;
- ambiguous-provenance findings;
- false-completion-risk findings;
- ineffective-retry findings;
- bounded recommendations.

Every finding must reference one or more computation results.

### 6.3 Projection Layer

The Projection Layer compresses computation and finding outputs into a process-state view consumable by Schumpeter or another client.

Example projection:

```text
Current process state:
- observed lifecycle stage: verification
- completed required activities: 5 / 6
- missing required activity: regression_test_completed
- temporal violations: 1
- unresolved evidence claims: 2
- recommended next action: request regression-test evidence
```

### 6.4 Import boundary

Required dependency direction inside PIX:

```text
contracts
   ↑
compute
   ↑
intelligence
   ↑
projection / engine / api
```

Rules:

- `compute` must not import `intelligence`;
- `intelligence` may consume compute-result contracts;
- `projection` may consume both;
- no module may import Schumpeter.

---

## 7. Neutral Data Contracts

PIX must not read Schumpeter's database directly. Schumpeter converts its OCEL persistence into neutral PIX contracts.

Initial contract shape:

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

@dataclass(frozen=True)
class ProcessEvent:
    event_id: str
    activity: str
    timestamp: datetime
    attributes: Mapping[str, object]

@dataclass(frozen=True)
class ProcessObject:
    object_id: str
    object_type: str
    attributes: Mapping[str, object]

@dataclass(frozen=True)
class EventObjectRelation:
    event_id: str
    object_id: str
    qualifier: str | None

@dataclass(frozen=True)
class ObjectObjectRelation:
    source_object_id: str
    target_object_id: str
    qualifier: str | None

@dataclass(frozen=True)
class ProcessDataset:
    events: tuple[ProcessEvent, ...]
    objects: tuple[ProcessObject, ...]
    event_object_relations: tuple[EventObjectRelation, ...]
    object_object_relations: tuple[ObjectObjectRelation, ...]
```

Contracts may evolve, but changes must remain explicit and versioned.

---

## 8. Computation and Finding Contracts

### 8.1 Computation result

```python
@dataclass(frozen=True)
class ComputationResult:
    computation_id: str
    operator_name: str
    operator_version: str
    status: str
    value: object
    source_event_ids: tuple[str, ...]
    source_object_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
```

Recommended statuses:

```text
computed
unavailable
invalid_input
```

A failed or unavailable computation must not silently become `False`, zero, or an empty list.

### 8.2 Process finding

```python
@dataclass(frozen=True)
class ProcessFinding:
    finding_id: str
    rule_id: str
    finding_type: str
    severity: str
    statement: str
    computation_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    recommended_action: str | None
    withdrawal_condition: str | None
```

Every finding must cite its computational basis.

### 8.3 Integrated analysis result

```python
@dataclass(frozen=True)
class PIXAnalysisResult:
    computations: tuple[ComputationResult, ...]
    findings: tuple[ProcessFinding, ...]
    process_state: object | None
    unavailable_computations: tuple[str, ...]
```

---

## 9. Initial Operator Catalog

PIX v0.1 should implement only operators needed by a real Schumpeter audit.

### 9.1 Required initial operators

1. `project_events_by_object`
2. `reconstruct_trace`
3. `check_relation_integrity`
4. `check_temporal_constraints`
5. `compute_lifecycle_completeness`
6. `compute_evidence_lineage`
7. `compute_retry_recovery_metrics`

### 9.2 Initial findings

1. `missing_lifecycle_activity`
2. `temporal_order_violation`
3. `dangling_relation`
4. `orphan_evidence`
5. `ambiguous_provenance`
6. `false_completion_risk`
7. `ineffective_retry`

### 9.3 Explicitly excluded from v0.1

- automatic process discovery;
- Petri-net discovery;
- full object-centric conformance checking;
- predictive monitoring;
- causal inference;
- machine-learning anomaly detection;
- automatic policy mutation;
- automatic skill learning;
- LLM-based judging;
- general industrial-process ontology;
- remote service or daemon mode;
- graph-database dependency.

---

## 10. Public API

PIX should expose explicit and integrated APIs.

### 10.1 Explicit pipeline

```python
computations = pix.compute(
    dataset=dataset,
    operators=[
        "relation_integrity",
        "trace_reconstruction",
        "temporal_conformance",
        "evidence_lineage",
    ],
)

findings = pix.interpret(
    computations=computations,
    rule_set=rule_set,
)

projection = pix.project(
    computations=computations,
    findings=findings,
)
```

### 10.2 Integrated pipeline

```python
analysis = pix.analyze(
    dataset=dataset,
    rule_set=rule_set,
)
```

The integrated API must internally preserve:

```text
compute → interpret → project
```

---

## 11. Schumpeter Integration Contract

Schumpeter should contain only an adapter and domain-specific rule profile.

Recommended Schumpeter side:

```text
Schumpeter/
└── src/
    └── schumpeter/
        └── integrations/
            └── pix/
                ├── dataset_adapter.py
                ├── rule_profile.py
                ├── result_mapper.py
                └── service.py
```

Responsibilities:

- `dataset_adapter.py`
  - converts Schumpeter OCEL data into `ProcessDataset`;
- `rule_profile.py`
  - defines Schumpeter-specific lifecycle and evidence rules;
- `result_mapper.py`
  - maps PIX analysis into Schumpeter audit inputs;
- `service.py`
  - controls the invocation boundary.

PIX must not decide whether a Schumpeter mission is completed. It supplies process facts and findings. Schumpeter applies mission policy.

Canonical boundary:

```text
PIX = process facts, computations, findings
Schumpeter = mission policy and action decision
```

---

## 12. First Vertical Slice

The first vertical slice must prove that PIX improves an actual audit decision.

Recommended candidates:

### Candidate A — Provider lifecycle audit

Expected order:

```text
provider_call_started
→ provider_call_completed
→ assistant_response_recorded
→ route_decision_recorded
```

Required cases:

- fully conformant trace;
- all events present but order incorrect;
- provider completion missing;
- provider identity ambiguous;
- response recorded without provider provenance.

### Candidate B — Failing-test mission audit

Required process:

```text
mission_started
→ failure_reproduced
→ code_changed
→ target_test_completed
→ regression_test_completed
→ verification_completed
→ mission_completed
```

Required cases:

- full evidence and completion;
- target test passes but regression test absent;
- test-result text exists without test-execution lineage;
- code changed outside the permitted scope;
- repeated retry without strategy change.

Only one candidate should be implemented first. Do not start both simultaneously.

---

## 13. Development Principles

### 13.1 Vertical-slice rule

A feature is not complete merely because a model or schema exists.

A complete feature must include:

```text
input fixture
→ computation
→ finding
→ public API result
→ tests
→ consumer-facing example
```

### 13.2 Evidence-first rule

- every finding references computations;
- every computation references source events or objects;
- assumptions are explicit;
- `UNKNOWN` and `unavailable` are first-class states.

### 13.3 Determinism rule

The same normalized input and operator version must produce the same output.

### 13.4 No unsupported composite score

Do not create a single “PI Score,” “Audit Score,” or “Agent Intelligence Score” until its predictive validity is empirically demonstrated.

Prefer decomposed outputs:

```text
trace completeness: fail
temporal conformance: fail
relation integrity: pass
required evidence coverage: 3 / 5
recovery effectiveness: unavailable
```

### 13.5 No speculative framework growth

A new operator may be added only when:

- a real audit problem requires it;
- an acceptance test can be written;
- its result changes or clarifies an actual decision.

---

## 14. Testing Strategy

### 14.1 Unit tests

Each operator must have positive, negative, malformed-input, and unavailable-input tests.

### 14.2 Contract tests

Test that:

- immutable contracts behave predictably;
- timestamps are normalized;
- unknown references are rejected or reported;
- invalid relations do not disappear silently.

### 14.3 Integration tests

Test the complete flow:

```text
ProcessDataset
→ PIX compute
→ PIX intelligence
→ process-state projection
```

### 14.4 Schumpeter integration tests

These belong in Schumpeter, not PIX:

```text
Schumpeter OCEL fixture
→ Schumpeter adapter
→ PIX
→ Schumpeter mission-audit decision
```

---

## 15. Risk Register

### Risk 1 — PIX becomes a Schumpeter trace utility

Control:

- no Schumpeter imports;
- neutral contracts only;
- no provider or mission names hardcoded in operators.

### Risk 2 — Compute and intelligence become entangled

Control:

- one-way internal imports;
- compute results independently testable;
- every finding references computation IDs.

### Risk 3 — PIX becomes an oversized research platform

Control:

- no operator without a real vertical-slice need;
- no empty modules for imagined future capability;
- no process-discovery or ML work in v0.1.

### Risk 4 — The adapter becomes the actual intelligence layer

Control:

- adapter performs translation only;
- domain rules remain declarative;
- calculations remain inside PIX;
- final mission policy remains inside Schumpeter.

### Risk 5 — Incorrect process semantics produce false confidence

Control:

- assumptions are explicit;
- unknown and unavailable states remain visible;
- counterexample fixtures are mandatory;
- no causality claims from mere sequence correlation.

---

## 16. Decision Classification

### Confirmed facts

- A complete general-purpose OCPX or PIG implementation does not currently exist.
- The prior architecture contained event, object, relation, trace, and OCEL foundations.
- The missing capability is deterministic process computation and evidence-aware interpretation.
- PIX is intended to be independent from Schumpeter while serving it as the first consumer.

### Data-based interpretation

- Consolidating OCPX and PIG into one PIX project reduces premature project and contract overhead.
- Keeping compute and intelligence as internal layers preserves testability and future extraction options.
- A sibling repository is more appropriate than embedding PIX inside Schumpeter.

### High-probability hypothesis

- PIX's first measurable value will come from detecting temporal violations, evidence gaps, and false completion rather than advanced process discovery.

### Uncertain / requires validation

- The degree to which PIX improves mission success or reduces false completion has not yet been measured.
- Reuse outside Schumpeter must be demonstrated rather than assumed.

---

## 17. Withdrawal and Reassessment Conditions

Reconsider the architecture if:

- most operators require direct knowledge of Schumpeter internals;
- adapter code becomes larger than the computation engine;
- package separation materially blocks the first vertical slice;
- compute and intelligence require incompatible release cycles;
- PIX adds no measurable audit value over direct constraints or SQL queries;
- results cannot be reproduced deterministically;
- findings routinely lack computational evidence.

Review this architecture after:

- the first 6–7 operators are implemented;
- one vertical slice is completed;
- 20–30 representative mission audits are evaluated.

---

## 18. PIX v0.1 Exit Criteria

PIX v0.1 is complete only when:

- the repository and package are named `PIX` and `pix`;
- neutral contracts exist and are tested;
- at least one object projection works;
- trace reconstruction works;
- relation integrity is computed;
- temporal constraints are computed;
- lifecycle completeness is computed;
- evidence lineage is computed;
- at least four findings are generated from computations;
- every finding references computations;
- the integrated `analyze()` API works;
- one vertical slice is demonstrated;
- documentation and operator catalog are present;
- all focused and regression tests pass;
- PIX contains no Schumpeter imports.

---

## 19. Source Lineage

This baseline consolidates concepts previously discussed in:

- `process_intelligence_digital_twin_concept.md`
- `chanta_research_group_schumpeter_bridge_guide.md`
- `ChantaGrowthKernel_ProcessIntelligence_Architecture.md`
- `schumpeter_docs_v3.9_to_v4.0.md`
- `Schumpeter-Architecture-Specification-(for-ChantaGrowthKernel).txt`
- `ChantaCore Codex Prompt Generation Standard.pdf`

These documents are historical design sources. This document is the canonical starting context for the new PIX project unless superseded by a later explicit PIX architecture decision.

---

## 20. Final Definition

**PIX is an independent, deterministic Process Intelligence computation and interpretation engine that converts object-centric event data into reproducible process facts, evidence-linked findings, and compact process-state projections. Schumpeter remains responsible for mission policy and action decisions.**
