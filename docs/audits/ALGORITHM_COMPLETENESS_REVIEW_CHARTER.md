# PIX Algorithm Completeness Review Charter

**문서 상태:** Review charter + **1차 검증 결과 첨부** (Ashlar 합본)  
**기준일:** 2026-09-26 (Asia/Seoul)  
**Branch under review:** `feat/ocel-readers-v0.2.0` (package **0.5.0**, tip `8a669844e4781757a22f8caa0ff45f3ad6a30943`)  
**관련 handoff:** Schumpeter `docs/audits/ASHLAR_DEVTEAM_BASELINE_2026-09-26.md` (동일 일자)  
**PR:** https://github.com/riesling-29/PIX/pull/1

## 목적

Vera가 git에서 읽어 취약점·계약 빈틈을 점검할 수 있도록, PI Scientist(Provenance)와 Data Scientist(Fathom)가 **알고리즘 완결성**을 면밀히 검증하고 결과를 문서화한다.

## 비목표

- Standalone Schumpeter Agent 제품 설계
- pm4py/ocpa를 런타임 의존으로 재도입
- Schumpeter가 PIX operator를 휴리스틱으로 대체

## 검증자가 채울 산출물

각 항목에 **confirmed fact / inference / unknown** 을 구분할 것.

1. Public operator / API inventory (`pix.api`, analysis/model 결과 계약 포함)
2. Stub 또는 UNAVAILABLE 목록 (`compute`/`intelligence` 포함)
3. Discovery / conformance / visualization 의미론 완결성·손실 보고
4. Determinism / digest / temporal identity 회귀 위험
5. 테스트 공백 (golden / property / metamorphic / statistical)
6. Vera용 취약점 후보 (우선순위 P0–P2)

## 충돌 방지

Vera와 병행 개발 중. 코드 변경 PR을 열기 전에 Ashlar에게 브랜치·경로 충돌을 알린다. 기본은 **읽기·문서·이슈/코멘트**; 코드 수정은 Ashlar 승인 후.

## 상태 (2026-09-26)

| 축 | 담당 | 상태 | 첨부 |
|---|---|---|---|
| PI 계약·의미론·Skill 최소 표면 | Provenance | 1차 완료 (read-only) | Appendix A |
| DS 재현성·테스트·PASS 프로토콜 | Fathom | 1차 완료 (read-only, pytest 미재실행) | Appendix DS |

**Ashlar 합본 메모:** 두 축 모두 코드 수정 PR 없음. Vera 다음 작업은 P0 golden/digest·approx/genetic sensitivity, ImportResult/canonical/stub 가짜 COMPUTED·OCPN observational 오해 방지.

---

## Appendix A — PI findings (Provenance) · 2026-09-26

**Author:** Provenance (PI Scientist)  
**Basis:** local read-only review of `feat/ocel-readers-v0.2.0` @ `8a66984` / package `0.5.0`  
**Claim labels:** [사실] confirmed in code/docs · [추론] contract judgment · [알 수 없음] not evidenced in this pass  
**Note:** DS축(재현성·수치·평가 프로토콜)은 Fathom 초안과 합칠 것. 본 섹션은 PI 의미론·계약·Skill 표면만 다룬다. PIX PR#1에 Provenance가 직접 쓰지 않음 — Ashlar 병합용.

### A.0 Executive summary

1. [사실] Canonical OCEL: typed model → `build`(무수리) → `validate` → Canonical V1 bytes → SHA-256. invalid candidate는 digest 없음.
2. [사실] `import_info`는 OCEL equality/hash 및 digest 경로에서 제외.
3. [사실] `ImportResult` status 불변식 엄격. `ImportFormat`의 TABLE_*는 OCEL loader가 아님(`pix.io` + 명시적 mapping).
4. [사실] 공개 분석 표면은 `pix.api`(+ root `import_log`/`read_log`). `case_centric`/`object_centric`는 대형 named-profile. `intelligence/*` 및 다수 `compute/*` owner는 empty stub.
5. [사실] OCPN discovery는 observational(수용 witness)이며 joint soundness·normative joint cardinality가 아님.
6. [사실] `ComputeStatus` ∈ {computed, partial, unavailable, invalid_input}; 실패를 0/False/빈 목록으로 위장 금지.
7. [사실] union-2026-09-15 registry: native_profile 126 / partial 141 / `reference_replacement_verified` **0**.
8. [추론] Schumpeter Skill은 아래 A.4 최소 표면만 pin; mining 확장·stub은 기본 UNAVAILABLE.
9. [추론] Vera 병행 최대 위험: identity/status invariants, Case↔OCEL 암묵 변환, IM 프로파일 혼동, OCPN 과대주장, stub 가짜 COMPUTED.
10. [알 수 없음] 본 pass에서 전체 pytest/성능 매트릭스는 재실행하지 않음.

### A.1 Public operator / API inventory

| Surface | Role | Label |
|---|---|---|
| `pix` root | `__version__`, `import_log`, `read_log` | [사실] |
| `pix.api` | Facade: OCEL I/O, case traces/mappings, native discovery/conformance/constraints, `engine.compute`, model/result persistence | [사실] |
| `pix.ocel` | model/build/validate/canonical/ingest/export | [사실] |
| `pix.results` / `pix.models` | versioned analysis-result & model JSON (allowlist; digests ≠ signatures) | [사실] |
| `pix.case_centric` / `pix.object_centric` | broad mining extension (named profiles) | [사실] |
| `pix.compute.__all__` | narrow subset only — full operators via `pix.api` | [사실] |

Skill에 권장하는 최소 admit 목록은 A.4.

### A.2 Stub 또는 UNAVAILABLE

**Empty stub owners** [사실] (`__all__` empty, “not implemented”):  
`compute/{integrity,lifecycle,lineage,object_projection,recovery}.py` · `intelligence/{__init__,diagnostics,findings,recommendations,rules}.py`

**의미상 UNAVAILABLE / 기본 deny** [추론]:  
광범위 case_centric·object_centric extras(IMf/IMd를 Skill 기본 경로에 넣기, genetic/privacy/streaming/embeddings, SAW를 기본 discovery로), 암묵 CaseLog↔OCEL, Hub/auth, “PM4Py-equivalent” 주장 (`reference_replacement_verified==0`).

**OCPN** [사실]: witness 실패·state bound → `UNAVAILABLE`/`PARTIAL` + issues.

### A.3 Discovery / conformance / visualization 의미론·손실

| Axis | Case-centric | Object-centric |
|---|---|---|
| Input | `CaseLog` (XES/MXML/mapped); source order, empty traces | Canonical `OCEL` |
| Bridge | 명시적 `to_ocel` — `import_log`에서 silent XES→OCEL 없음 [사실] | 명시적 object→case projection (v2 metadata; v1 cache 재사용 금지 [사실]/remediation) |
| Discovery | `pix.im.weighted.v1`, `pix.imf.*`, `pix.imd.*` 등 | native `pix.inductive_cut.v1` / `pix.im.v1` via OCPN; SAW `pix.observed_saw.v1` |
| Conformance | classical align/replay/precision | joint `align_object_log`; object token replay ≠ flattened replay |

**손실·오용** [사실]+[추론]:  
flattened case를 합산하면 shared event 이중계산; OCPN≠joint soundness; tie time은 order deferred; zero denominator/search limit는 issue로 남김(수치 0 fitness 금지); `discover_process_tree`는 IMf/IMd 미지원 — case_centric inductive의 별도 profile; visualization은 Graphviz WASM 기본이나 완전 parity 미주장.

### A.4 Determinism / digest / temporal identity 회귀 위험

| Risk | Contract break |
|---|---|
| invalid candidate에 digest | 금지; SEMANTIC_INVALID는 digest 없음 |
| equality에 `import_info` 포함 | provenance-independent identity 파괴 |
| validate에서 int→float widen / build에서 drop·dedup | 증거 은닉 |
| Object attr uniqueness가 UTC fold 무시 | REV-01 회귀 |
| projection v1 cache after v2 | identity migration |
| OCPN “sound” / joint cardinality marketing | observational 계약 모순 |
| `UNAVAILABLE`→0 fitness | status envelope 위반 |
| auto XES→OCEL in `import_log` | 명시적 거절 경로 |
| intelligence stub을 COMPUTED로 채움 | false confidence |
| `pix.im.v1` ↔ case IMf 혼동 | 서로 다른 알고리즘/identity |
| RESULT_VERSION / schema allowlist drift | decode 실패·unsafe types |

### A.5 테스트 공백 (PI 관점)

[사실] 저장소에 `tests/ocel`, golden canonical vectors, import/native suites가 존재한다고 문서·트리에 기록됨.  
[알 수 없음] 본 pass에서 suite를 재실행하지 않아 현재 checkout의 pass/fail은 미확인.  
[추론] Skill 게이트로 우선 고정할 것: ImportResult invariants, canonical golden, no silent Case↔OCEL, OCPN observational issue text, IM profile string isolation, results allowlist.

(통계·metamorphic·수치 안정성은 Fathom DS 축에 위임.)

### A.6 Vera용 취약점 후보 (우선순위)

**P0**
- `src/pix/ocel/ingest/contract.py` — `ImportResult` status↔candidate↔digest 결합
- `src/pix/ocel/canonical/v1.py` + `docs/specifications/PIX_OCEL_CANONICAL_V1.md` — byte layout / eligibility
- `src/pix/ocel/model.py` — `import_info` compare/hash; Object UTC-instant uniqueness
- `src/pix/io.py` / `src/pix/ocel/ingest/reader.py` — TABLE_* vs OCEL loader; XES reject path; no silent conversion

**P1**
- `src/pix/ocel/build.py`, `validate.py` — no-repair / no-widen / disconnected-OK / duplicate relations
- `src/pix/compute/context.py`, `src/pix/contracts/result.py` — invalid OCEL reject; ComputeStatus coexistence
- `src/pix/compute/ocpn_discovery.py`, `contracts/ocpn_discovery.py`, `contracts/discovery.py` — observational bounds; only `pix.inductive_cut.v1`/`pix.im.v1` on api tree
- `src/pix/case_centric/inductive.py` — separate IM/IMf/IMd profile strings
- `src/pix/object_centric/conformance.py` — joint vs flattened operator_ids
- `src/pix/results.py`, `src/pix/_mining_registry.py` — schema allowlists

**P2**
- `src/pix/intelligence/*` 및 stub `compute/*` — “완성” 시 가짜 success
- `src/pix/object_centric/discovery.py` — SAW histogram ≠ probabilities
- projection identity / REV-02 v2 metadata

### A.7 Schumpeter Skill 최소 PIX 표면 [추론]

**Admit (pin profile + status branch):**  
`import_log`/`read_log` · `pix.ocel.{import_ocel,read_ocel,export_ocel,OCEL,ImportResult,canonical_digest,validate,build}` · `pix.api`: `case_traces`, mappings, `reconstruct_traces`, `discover_dfg`/`discover_ocdfg`, `measure_temporal`, `discover_executions`/`discover_variants`, `discover_process_tree`+`DiscoverySpec`, `discover_ocpn`, `process_tree_to_petri_net`, `align_traces`/`replay_traces`, `align_object_log`, `measure_prefix_precision`, `measure_object_context`, `evaluate_constraints`, `write_result`/`read_result`, `write_model`/`read_model`.

**Default UNAVAILABLE:** A.2 stub·확장 프로파일 전부, 암묵 Case↔OCEL, verified PM4Py replacement claim.

### A.8 pm4py/ocpa 대체 관점 [사실] (registry)

- scope-01: early matrix (다수 `absent`) — 현재 부재 판단에 단독 사용 금지, union 대조 필요.
- union-2026-09-15: native/partial 다수, **verified replacement 0**.
- 필수 PI 경로(native/partial로 존재): import·traces·DFG/OCDFG·temporal·IM/inductive_cut·observational OCPN·align/replay·precision·constraints·persistence.
- 부재/미검증 고수요: api tree의 noise-threshold IMf, Alpha/Heuristics/ILP/Genetic verified, 다수 precision/anti-align, full OC filter suite 등.

### A.9 권고 (코드 변경 없음)

1. Skill 계약에 A.7 allowlist + status 처리 고정.
2. BE/DB: `ImportResult`/`ComputationResult` envelope + digests 유지; SEMANTIC_INVALID candidate만 저장 금지.
3. Vera PR: P0–P1 경로 변경 시 identity golden 게이트.
4. 온보딩: `pix.api` vs `compute.__all__` vs stubs vs case IMf.
5. registry는 union/models-w4 우선; verified 주장 금지.
6. 본 Appendix를 charter에 붙인 뒤 Fathom DS 섹션과 교차 참조.



---

## Appendix DS — Algorithm Completeness (stats / reproducibility / tests / protocol)

- **Auditor:** Fathom (Data Scientist)
- **Scope tip:** `feat/ocel-readers-v0.2.0` @ `8a669844e4781757a22f8caa0ff45f3ad6a30943` / package **0.5.0**
- **Axis:** DS only (maps charter items **3–6**, test gaps in **5**). PI contracts → Provenance.
- **Cross-ref:** Schumpeter `docs/audits/ASHLAR_DEVTEAM_BASELINE_2026-09-26.md` §5.3
- **Method:** read-only code/test/docs review; **pytest not re-run** in this pass.

### 사실 (Fact)

- **Version / tip:** `pyproject.toml` `version = "0.5.0"`; tip commit message references OCEL temporal identity fix. Charter PR#1 is docs-only on `cursor/algorithm-completeness-charter-5a98`.
- **Layout:** `src/pix/{api,compute,case_centric,object_centric,viewer,ocel,contracts,…}`; `tests/` ≈197 `test_*.py`.
- **Temporal (`pix.compute.temporal.measure_temporal`):** durations via integer µs (`_microseconds`); mean as `mean_numerator`/`mean_denominator` (`DurationSummary` in `contracts/analysis.py`); outputs `sorted`; weighting `event_pairs` vs `occurrences`; ties require explicit `tie_policy` (`reject`|`event_id`). Tests: order invariance, year-scale no float-seconds (`tests/compute/test_temporal.py`).
- **Variants (`pix.compute.variants.discover_variants`):** exact canonical labeling; budget exceed → `UNAVAILABLE` (no partial groups); `sorted` execution IDs; SHA256 `variant_id`/`canonical_signature`. Coverage: `tests/compute/test_variants.py`.
- **Frequency / DFG (`pix.compute.dfg.discover_dfg`):** `Counter` + `sorted` activities/edges; occurrence counts.
- **Viewer:** heavy `sorted` + compact `json.dumps` in `viewer/adapter.py`, `visual_object_adapters.py`; some permute-invariance tests (`tests/viewer/test_visual_object_adapters.py`).
- **Stochastic (seeded):** `genetic_miner`, `embeddings`, `object_centric.simulation`, `subset_conformance_approximation`, timed/resource simulation — `Random(spec.seed)` (or derived). **No** `hypothesis` in `pyproject.toml` / `uv.lock`.
- **Golden (narrow):** `tests/ocel/golden/canonical_v1/{empty,representative}.{json,sha256}`; DFG text golden (`tests/model_io/test_dfg.py`); hand OCDFG goldens (`tests/object_centric/test_graph_comparison.py`). **Not** discovery/conformance/viz semantic result vectors.
- **Property-like:** seeded oracles (not Hypothesis), e.g. `tests/compute/test_*_oracle.py` (~15 files use `Random`).
- **Metamorphic (sparse):** input-permutation / order-invariance in compute discovery·IM·trace·object conformance·enrichment (~14 files); no named metamorphic suite.
- **Float path:** `case_centric/statistics.py` / `business_time.py` use `timedelta.total_seconds()` → float / `NumericSummary` — distinct from compute temporal integer path.
- **Prior “completeness” docs** (`docs/reports/2026-09-18_PIX_PM4PY_OCPA_COMPLETION_ASSESSMENT.md`, `docs/version/2026-09-15_NATIVE_MINING_VALIDATION.md`) measure **feature-row coverage / suite green**, not statistical PASS criteria.

### 추론 (Inference)

- Core **compute** discovery/DFG/temporal/variants aim for **byte-stable, order-insensitive** results under fixed OCEL+spec; residual non-determinism risk is mainly **seeded stochastic** miners/embeddings/approx conformance and **Python float case-duration stats**.
- Suite pass counts or PM4Py/OCPA A/B row % **overstate** statistical algorithm-completeness without cross-operator golden digests, Hypothesis properties, and sample-size/selection-bias protocols for approx & genetic paths.
- Visualization completeness (DS) = **panel/export identity under record permutation**, not Graphviz layout pixel identity.

### 알 수 없음 (Unknown)

- pytest not re-run; historical 8,362-pass figure is local evidence only.
- Production-scale sample-size / memory limits; seed portability across CPython minors for genetic/embeddings.
- Whether all `case_centric`/`object_centric` frequency surfaces sort deterministically like `compute`.
- Full stub vs `UNAVAILABLE` inventory (charter §2) — Provenance/Vera.

### Vera용 실험설계·통계 공백 (경로 · 증상 · 재현 힌트)

| Pri | Hole | Path | Symptom | Repro hint |
|---|---|---|---|---|
| **P0** | No golden digests for DFG/temporal/`VariantSet`/viewer panel IDs on fixed fixtures | Goldens today: `tests/ocel/golden/canonical_v1/*`, `tests/model_io/test_dfg.py`, `tests/object_centric/test_graph_comparison.py` | Semantic compute/viz outputs can regress without digest fail | Pin fixture OCEL → run `discover_dfg` / `measure_temporal` / `discover_variants` / one viewer panel id set → commit digest; assert on tip |
| **P0** | Approx / genetic / embeddings: seed+sample-size sensitivity & selection bias not protocolized | `src/pix/.../conformance_approximation.py` (`Random(spec.random_seed).sample`); `genetic_miner.py`; `embeddings.py` | Same seed+n may look stable while n/selection bias undocumented; population claims unsafe | Sweep seed×n; report omission counts; refuse biased sample (see `test_binding_cap_…_sampled_refuses_bias` pattern) |
| **P1** | Dual duration semantics → cross-API numeric drift | `pix.compute.temporal` (int µs) vs `case_centric/statistics.py`, `business_time.py` (`total_seconds()` float) | Year-scale or fine-grain durations disagree across APIs | Same log through both paths; compare means; year-scale fixture |
| **P1** | No Hypothesis / metamorphic *suite*; permute tests ad hoc | no `hypothesis` dep; sparse `permuted` asserts (~14 files) | Order bugs outside covered operators slip | Add Hypothesis strategies on event/object/E2O permutations for public compute surfaces |
| **P1** | Variant budget exceed → empty `UNAVAILABLE` misread as “no variants” | `pix.compute.variants` / `variants.py` `limit_exceeded` | Consumers treat UNAVAILABLE like empty success | Assert status≠success when `limit_exceeded`; contract docs |
| **P2** | Oracle RNG tests ≠ property contracts | `tests/compute/test_*_oracle.py` | No shrinking, no CI budget fence | Replace/augment with Hypothesis + explicit deadline |
| **P2** | Completeness registries ≠ statistical PASS | `docs/reports/2026-09-18_PIX_PM4PY_OCPA_COMPLETION_ASSESSMENT.md`, `docs/version/2026-09-15_NATIVE_MINING_VALIDATION.md` | Green suite / row % read as algorithm-complete | Gate releases on protocol below, not coverage % alone |

### Draft evaluation protocol — “algorithm completeness” PASS (DS)

Operator family **PASS** only if **all** hold on pinned tip+fixtures:

1. **Determinism:** same OCEL bytes + operator_id/version + spec → identical `computation_id` / payload digest (or documented seed → identical draw sequence).
2. **Order metamorphic:** permute events/objects/E2O rows → identical analysis/viz contracts (ties: both `reject` and `event_id` policies tested).
3. **Exact vs approx label:** exact paths never emit partial groups on budget fail; approx/genetic paths declare seed, sample size, and **do not** claim population estimators without CI/sensitivity table.
4. **Numeric stability:** temporal means stay rational int µs (or documented float ε); no silent `total_seconds` loss on year-scale fixtures for compute path.
5. **Golden gate:** ≥1 committed golden vector per public compute surface used by Schumpeter Skill (DFG, temporal summary keys, variant signatures, one viewer panel id set).
6. **Anti-bias:** subset/approx selection reports omission counts; refusing biased sample is PASS.

**FAIL** if: unseeded RNG; float path used where contract claims exact; empty success masking `UNAVAILABLE`; suite-green without (1)–(5).

### 권고

Do **not** treat current feature-coverage % as DS completeness. Next Vera/test work: **P0 goldens** + **approx/genetic sensitivity harness**. Keep PI contract audit with Provenance.

