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
| PI 계약·의미론·Skill 최소 표면 | Provenance | 1차 완료 (read-only) | Appendix PI |
| DS 재현성·테스트·PASS 프로토콜 | Fathom | 1차 완료 (read-only, pytest 미재실행) | Appendix DS |

**Ashlar 합본 메모:** 두 축 모두 코드 수정 PR 없음. Vera 다음 작업은 P0 golden/digest·approx/genetic sensitivity, ImportResult/canonical/stub 가짜 COMPUTED·OCPN observational 오해 방지.

---

## Appendix PI — PIX PI 알고리즘 완결성 검증 (Provenance)

- 기준: `feat/ocel-readers-v0.2.0` / package `0.5.0` / `/workspace/PIX`
- 일자: 2026-09-26 (Asia/Seoul)
- 성격: read-only. PIX PR#1 audit 문서 후속 첨부용 초안.

주장 표기: [사실] / [추론] / [알 수 없음]

## Executive summary

1. [사실] Canonical OCEL 경로: typed model → build(무수리) → validate → Canonical V1 → SHA-256. invalid candidate는 digest 없음.
2. [사실] `import_info`는 equality/hash/digest에서 제외.
3. [사실] `ImportResult` status 불변식 엄격. TABLE_*는 enum에 있으나 OCEL loader가 아님(`pix.io`+mapping).
4. [사실] 공개 분석 표면은 `pix.api`(+`import_log`/`read_log`). `case_centric`/`object_centric`는 대형 named-profile. `intelligence/*` 및 일부 `compute/*`는 stub.
5. [사실] OCPN discovery는 observational(수용 witness)이며 joint soundness가 아님.
6. [사실] `ComputeStatus`: computed/partial/unavailable/invalid_input. 실패를 값으로 위장 금지.
7. [사실] scope-01 대부분 absent; union-2026-09-15는 native_profile 126 / partial 141 / reference_replacement_verified **0**.
8. [추론] Schumpeter Skill은 최소 `pix.api`+OCEL+results만 pin. mining 확장·stub은 기본 UNAVAILABLE.
9. [추론] Vera 병행 최대 위험: identity/status, Case↔OCEL 암묵 변환, IM 프로파일 혼동, OCPN 과대주장, stub 가짜 COMPUTED.
10. [알 수 없음] 이 감사에서 전체 pytest/성능 매트릭스는 재실행하지 않음.

## 1) OCEL build / validation / Canonical / ImportResult

보장 [사실]: frozen model; build는 normalize/sort만; validate는 타입·참조·중복 관계; disconnected entity 허용; digest는 semantic valid만; provenance 독립 동일성.

빈틈 [사실]+[추론]: declared attr 전부 출현 강제 없음; WARNING 레벨은 validate가 사실상 error만; ImportFormat TABLE_* 메시지 혼동; 직접 `OCEL(...)`는 invalid 가능.

## 2) case_centric vs object_centric

[사실] Case: CaseLog 입력, 명시적 to_ocel. OC: OCEL 입력, joint align vs flattened replay 분리. OCPN은 observational. IMf/IMd는 api tree miner가 아니라 case_centric named profile.

오용 위험 [추론]: OCPN을 joint soundness로 해석; `pix.im.v1`과 case IMf 동일시; UNAVAILABLE→0 fitness.

## 3) pix.api vs stubs

[사실] BE/DB는 `pix.api`·`ImportResult`/`ComputationResult` envelope 기준. `pix.compute.lineage`/`pix.intelligence.*`는 동작 가정 금지. SEMANTIC_INVALID candidate를 운영 진실로 저장 금지.

## 4) Schumpeter Skill 최소 표면 [추론]

Admit: import/read_log, ocel I/O·build·validate·canonical_digest, case_traces, DFG/OCDFG/temporal, executions/variants, discover_process_tree(DiscoverySpec), discover_ocpn, align/replay(case+object), prefix precision, object context, constraints, write/read result·model. 항상 status 분기.

UNAVAILABLE(기본): intelligence.*, stub compute owners, 광범위 case/object 확장 프로파일, 암묵 Case↔OCEL, PM4Py-equivalent 주장.

## 5) pm4py/ocpa 대체

[사실] verified replacement 0. 필수 PI 경로(native/partial)는 import·trace·DFG/OCDFG·IM/inductive_cut·observational OCPN·align/replay·precision·constraints·persistence. 부재/미검증: api IMf noise-threshold, Alpha/Heuristics/ILP/Genetic verified, 다수 precision/anti-align, full OC filter 등.

## Vera 취약점 후보 (경로)

- `src/pix/ocel/ingest/contract.py` ImportResult invariants
- `src/pix/ocel/model.py` import_info / Object UTC uniqueness
- `src/pix/ocel/build.py`, `validate.py`, `canonical/v1.py`
- `src/pix/ocel/ingest/reader.py`, `src/pix/io.py`
- `src/pix/compute/context.py`, `contracts/result.py`
- `src/pix/compute/ocpn_discovery.py`, `contracts/discovery.py`
- `src/pix/case_centric/inductive.py`, `object_centric/{discovery,conformance}.py`
- `src/pix/results.py`, `_mining_registry.py`
- `src/pix/intelligence/*`, stub `compute/*`

## 권고 (코드 변경 없음)

1. Skill 계약에 §4 allowlist+status 처리 고정
2. BE/DB는 status+digest envelope 유지
3. Vera 경로 변경 PR은 identity golden 게이트
4. 온보딩: api vs compute.__all__ vs stubs vs IMf
5. registry는 union/models-w4 우선; verified 주장 금지
6. PIX PR#1 audit 문서에 본 보고 후속 첨부 가능 (경로 충돌 확인 후)



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

