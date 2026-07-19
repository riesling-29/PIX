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