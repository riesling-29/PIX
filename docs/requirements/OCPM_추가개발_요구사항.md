# PIX OCPM 추가 개발 요구사항

| 항목 | 내용 |
| --- | --- |
| 문서 성격 | **추가 OCPM 요구** (알고리즘 완결성 charter 대체 문서 아님) |
| 작성 | Provenance (PI Scientist) |
| 기준일 | 2026-09-27 (Asia/Seoul, KST) |
| 대상 tip | `feat/ocel-readers-v0.2.0` @ `8a66984` / package **0.5.0** |
| 독자 | 대표님 · Ashlar(개발 파트장) · 개발팀 |
| 산출 형태 | 요구사항·갭 매트릭스·우선순위 백로그만. **코드 PR·FE/BE/DB 구현 지시 없음** |

### 이 문서가 아닌 것 (충돌 방지)

- [ALGORITHM_COMPLETENESS_REVIEW_CHARTER](../audits/ALGORITHM_COMPLETENESS_REVIEW_CHARTER.md) (**in-repo 포인터**) 및 Vera **P0 identity/status** 점검(ImportResult·Canonical digest·`import_info`·암묵 Case↔OCEL 등)을 **대체·중복 지시하지 않는다.**
  - 이중 링크(workspace 합본): `/workspace/PIX-audits/ALGORITHM_COMPLETENESS_REVIEW_CHARTER_MERGED.md`
  - 핸드오프 원본: `/workspace/handoff-docs/ALGORITHM_COMPLETENESS_REVIEW_CHARTER.md`
- 완결성·취약점 후속은 charter / `PI_FOLLOWUP_SECTION_FOR_CHARTER.md` / Ashlar baseline을 **참조만** 한다.
- 본 문서는 **OCPM 이론·표준 대비 PIX 제품 계산 갭**과 **추가 must/should 요구**만 다룬다.

### 표기 규칙

| 표기 | 의미 |
| --- | --- |
| **[사실]** | 코드·docs/registry에서 확인 |
| **[이론]** | OCEL/OCPM 문헌·표준 기준선 (PIX 구현 주장 아님) |
| **[must]** | P0 필수 요구 (수락 기준 포함) |
| **[should]** | P1 권장 요구 |
| **[could]** | P2 여유 요구 |
| **[추론]** | 계약·우선순위 판단 (사실 아님) |
| **[알 수 없음]** | 본 pass에서 미검증 |

---

## 1. 배경·범위·비범위

### 1.1 배경

Object-Centric Process Mining(OCPM)은 단일 case 식별자 가정 대신, 이벤트가 **여러 유형의 객체**에 참여하는 로그(OCEL)를 대상으로 발견·적합성·성능·관계를 계산한다. PIX는 Water Mixing Capital의 **불변 OCEL 구축·검증·내보내기 및 결정론적 PI 계산 엔진**이며, 실시간 방출·Agent 운영은 Schumpeter 책임이다.

### 1.2 범위 (In scope)

- OCEL 2.x 메타모델 요소(E2O/O2O·qualifier·객체 속성 이력)를 **계산 입력으로 쓰는** 네이티브 OC 연산의 제품 요구
- OCDFG / EOG / OCPN(관측적) / joint·object·flattened conformance / OC 성능(EOG·OPERA) / 필터·관계 graph / projection 경계
- 기존 `pix.api`·`ComputationResult`·named profile과의 **정합** (새 의존성·wrapper 금지)
- 시각화(Gesso)에 넘길 **뷰 정체성·분모/연산자/observational 배지·projection 손실 배너·범례/접근성**을 포함한 표시 의미 (**OCPM-VIS-P0/P1**, FE 지시 아님)
- Fathom이 지원할 **지표·실험·sequence→PM 연결** 검증 요구

### 1.3 비범위 (Out of scope)

| 항목 | 이유 |
| --- | --- |
| ALGORITHM_COMPLETENESS charter / Vera P0 identity 작업 | 별도 트랙; 본 문서가 지시하지 않음 |
| PM4Py / OCPA / pandas **런타임 의존** 재도입 | 제품 경계 **[사실]** README·pyproject |
| Schumpeter 라이브 emission·Skill Hub·Agent 실행 | Schumpeter 소유 |
| `pix.intelligence.*`, `compute/{integrity,lifecycle,lineage,object_projection,recovery}` stub 채우기 | stub **[사실]**; OCPM 핵심 경로 아님 → P2 이후 또는 별도 기획 |
| FE/BE/DB 스키마·API 구현 지시 | 문서만; Keel/Coffer는 **범위 확대 시** |
| `reference_replacement_verified` 일괄 완료 선언 | registry **0행** **[사실]**; 대체 검증은 charter/union 트랙 |
| 가공 fitness·precision 수치 제시 | 본 pass 미측정 **[알 수 없음]** |
| Case-centric 전면 확장 (Alpha/Genetic/privacy 등) | OCPM 추가 요구 밖; 필요 시 별도 문서 |
| Casement FE 구현·새 layout 엔진(Cytoscape 등) | Graphviz WASM·Chevron·VisualizationDocument **확장**만; FE는 문서 최종 승인 후 |

---

## 2. 현황 요약 (사실, 코드 근거)

**검증 tip:** `/workspace/PIX`, branch `feat/ocel-readers-v0.2.0`, commit `8a66984`, `pyproject.toml` version `0.5.0`.

### 2.1 제품 역할

| 주장 | 근거 | 표기 |
| --- | --- | --- |
| PIX = 결정론적 PI 계산·해석; Schumpeter → PIX, PIX ↛ Schumpeter | `README.md` Dependency boundary | **[사실]** |
| 런타임에 PM4Py/OCPA/pandas 없음; optional excel/parquet만 | `pyproject.toml` dependencies | **[사실]** |
| Package 0.5.0 | `pyproject.toml` | **[사실]** |

### 2.2 로그·입출력

| 능력 | 위치 | 표기 |
| --- | --- | --- |
| OCEL 1 JSON/XML·classic SQLite; OCEL 2 JSON/XML/SQLite; OCEL **2.1.0pre4** compact CSV·CSV/Parquet bundle | `src/pix/ocel/ingest/`, `docs/design/2026-09-12-import-v050.md` | **[사실]** |
| XES/MXML → CaseLog; 표 매핑 → Case 또는 OCEL | `event_log/`, `tabular/`, `pix.io` | **[사실]** |
| Canonical V1 → SHA-256; invalid candidate는 digest 없음 | `docs/specifications/PIX_OCEL_CANONICAL_V1.md`, ocel build/validate | **[사실]** |
| OCEL 2.1 = pre4 프로파일; “최종 표준 완전 준수” 미선언 | import-v050 §3 | **[사실]** |

### 2.3 Object-centric 핵심 연산 (공개·네이티브)

| 연산 | 진입점 | Registry( OC 100행, 2026-09-15 ) | 표기 |
| --- | --- | --- | --- |
| OCDFG | `pix.api` / `compute.ocdfg.discover_ocdfg` | OC-OCDFG `native_profile` | **[사실]** |
| EOG(객체별 선후행 graph) | executions/variants·object_centric | OC-EVENT-GRAPH `native_profile` | **[사실]** |
| OCPN 발견 (관측적 수용 witness; joint soundness 아님) | `discover_ocpn`, `PIX_OCPN_DISCOVERY_V1.md` | OC-OCPN-DISCOVERY mixed native/partial | **[사실]** |
| SAW (관측 arc-weight) | `object_centric.discover_saw_net` | OC-SAW `native_profile` | **[사실]** |
| Joint alignment / object token replay / flattened replay | `align_object_log`, `replay_object_log`, flattened | ALIGN native; REPLAY native+partial; FLATTENED native | **[사실]** |
| Object context fitness/precision | `measure_object_context` | OC-CONTEXT **partial** | **[사실]** |
| EOG 성능 · OPERA token 성능 | `object_centric.performance` | EOG mostly native; TOKEN native+partial | **[사실]** |
| 관계 graph (interaction/descendant/…, ETOT, OTG) | `discover_object_graph` 등 | OC-RELATION-GRAPHS `native_profile` | **[사실]** |
| 필터·OLAP cube·enrichment·features | `object_centric/*` | FILTER mostly native; 일부 partial | **[사실]** |
| 명시적 object→case projection | `case_projection.project_object_cases` | OC-TRANSFORMS partial 행 다수 | **[사실]** |
| Viewer: Graphviz WASM 기본, OC variant chevron | `pix.viewer`, VISUALIZATION guides | **[사실]** |

**Registry 요약 (union-2026-09-15):** object_centric 100행 = `native_profile` 65 + `partial` 35; **`reference_replacement_verified` = 0** (전체 268행 기준도 0). **[사실]**  
행 수 ≠ 완성률. **[사실]** 문서 자체 경고.

### 2.4 Case-centric (OCPM 경계용 요약)

- `pix.case_centric` 대형 named-profile; CaseLog 입력, 명시적 `to_ocel`만. **[사실]**
- IM/IMf/IMd 등은 case 쪽 profile이며 api tree miner(`pix.im.v1` / inductive_cut)와 **동일시 금지**. **[사실]** charter·union.

### 2.5 Stub / 기본 UNAVAILABLE

빈 stub (`__all__` empty): `compute/{integrity,lifecycle,lineage,object_projection,recovery}.py`, `intelligence/*`. **[사실]**  
→ 본 OCPM 추가 요구의 P0에 **넣지 않음** (비범위).

### 2.6 선행 감사와의 관계

| 문서 | 역할 |
| --- | --- |
| ALGORITHM_COMPLETENESS charter + PI follow-up | identity·status·Skill allowlist·Vera P0 |
| union / OBJECT_CENTRIC_COVERAGE / models-w4 | 행별 native/partial |
| **본 문서** | 이론 기준선 → **추가** must/should 백로그 |

---

## 3. OCPM 이론·표준 기준선 (짧게)

### 3.1 표준·메타모델 **[이론]**

- **OCEL 2.0:** E2O·O2O, relationship qualifier, 객체 속성 변경(changes), JSON/XML/SQLite.  
  출처: [OCEL 2.0 specification](https://ocel-standard.org/2.0/ocel20_specification.pdf), [overview](https://www.ocel-standard.org/specification/overview/)
- **OCEL 2.1:** compact CSV + bundled CSV/Parquet ZIP (메타모델은 2.0 계열).  
  출처: [2.1 PDF](https://www.ocel-standard.org/2.1/ocel20_specification.pdf), [CSV](https://www.ocel-standard.org/specification/formats/csv/), [bundled](https://www.ocel-standard.org/specification/formats/bundled/)
- PIX는 **2.1.0pre4**에 고정. **[사실]** 최종 표준 인증 ≠ 현재 상태.

### 3.2 핵심 기법 축 **[이론]** (갭 매핑용; PM4Py는 **참조만**)

| 축 | 대표 개념 | 대표 문헌·도구 (참조) |
| --- | --- | --- |
| 발견 | OCDFG; Object-centric Petri nets (가변 arc) | van Aalst & Berti, *Discovering object-centric Petri nets*, FI 2020 |
| 적합성 | OCPN fitness/precision; joint binding; constraint monitoring | OCPA; PIX joint align / object replay |
| 성능 | EOG 기반 시각차; OPERA(token visit) — sync/pooling/lagging 등 | Adams et al., OPerA (arXiv:2204.10662) |
| 관계·멀티객체 | object interaction/descendant/inheritance/cobirth/codeath; ET-OT; OTG | pm4py.ocel `discover_objects_graph` 등 (갭 참조) |
| 실행·variant | connected component / leading object; graph isomorphism variants | OCPA / pm4py split_ocel |
| 필터·변환 | type/activity/cardinality/time-window; flatten vs keep multi-object | OCEL tooling 일반 |

**비고:** PM4Py/OCPA 기능을 PIX에 **의존성으로 넣자는 제안이 아니다.** 갭 식별용 기준선만이다.

---

## 4. 갭 매트릭스

상태: **Have** / **Partial** / **Missing** / **Out of scope (Schumpeter 또는 charter)**.  
근거는 주로 union OBJECT_CENTRIC_COVERAGE + 코드.

| OCPM 능력 | PIX 상태 | 근거 요약 | 비고 |
| --- | --- | --- | --- |
| OCEL 2.0 메타모델 ingest | **Have** | readers + validate | |
| OCEL 2.1 compact/bundle | **Partial** | pre4 고정; 최종 표준·웹요약 차이 명시 | P1 추적 |
| OCDFG (분모 프로파일) | **Have** | native; 분모 문서화·버전 고정을 should | P0 계약 |
| EOG ≠ OCDFG | **Have** | OC-EVENT-GRAPH native | |
| OCPN 발견 + 수용 witness | **Partial** | observational; soundness·normative cardinality 아님 | P0 계약 |
| SAW | **Have** | native | |
| OCCN / OCPN 변환 | **Partial** | MODEL-CONVERT partial | P1 |
| Joint alignment | **Have** | native | operator 분리 P0 |
| Object token replay | **Partial** | silent/flooding 정책 partial | P1 |
| Flattened replay | **Have** | joint와 **별 연산** | 혼동 금지 P0 |
| Object context prec/fit | **Partial** | OC-CONTEXT | P1 정의 고정 |
| Graph conformance (OCDFG) | **Have** | | |
| ET-OT/OTG 비교 | **Partial** | PM-OCEL-024 | P1 |
| EOG performance | **Have**~**Partial** | 요약 통계 partial | P1 |
| OPERA + model annotation | **Partial** | OC-PERF-005 | P1 |
| Relation graphs | **Have** | | |
| Executions CC/leading | **Have**~**Partial** | PM split-OCEL partial | P1 |
| Variant graph isomorphism | **Partial** | OC-EXEC-004/005 | P1 |
| Filtering suite | **Have**~**Partial** | time/lifecycle/perf filter partial | P1 |
| Object→case projection + 손실 영수증 | **Partial** | 존재하나 transforms partial 다수 | P0 |
| O2O enrichment / lifecycle qualifier | **Have**~**Partial** | lifecycle mark partial | P1 |
| Constraints / qualifiers | **Have** | | |
| Features / datasets | **Have**~**Partial** | | P2 |
| Action patterns/schedule | **Have** | 실행은 Schumpeter | Out (실행) |
| Live OCEL emission | **Out of scope** | Schumpeter | |
| Identity/digest/ImportResult | **Out of scope** | charter / Vera P0 | |
| Intelligence/lineage stubs | **Missing** (의도적) | stub 사실 | 비범위 |

---

## 5. 요구사항 백로그 (P0–P2)

> 본 절은 **요구 정의**다. 구현 일정·PR·Keel/Coffer 스키마 변경을 지시하지 않는다.  
> Vera P0(identity)와 ID·주제를 겹치지 않게 했다.

### 5.1 P0 — [must]

#### OCPM-P0-01 · OCPN 관측적 계약의 제품 표면 고정

- **문제:** 이론상 OCPN은 유용하나, PIX 구현은 **관측 구간·수용 witness**이며 joint soundness·규범적 cardinality가 아니다. 과대 해석 시 Skill/보고서 오용.
- **근거:** `PIX_OCPN_DISCOVERY_V1.md`; README; charter A.3. **[사실]** + van Aalst & Berti 2020 **[이론]**
- **수락 기준:**
  1. `discover_ocpn` 결과/issues에 `observational_cardinality`·`joint_cardinality_guarantee` (또는 동등 필드)가 **항상** 문서화된 의미로 노출.
  2. 공개 가이드·Skill 후보 문구에 “sound OCPN / 전체 fitness 보장” 표현 **금지** (문구 체크리스트).
  3. witness 한도 초과 시 `UNAVAILABLE`/`PARTIAL` + issue (0 fitness 위장 금지) — 기존 계약 재확인.
- **제안 소유:** Provenance (의미) · Fathom (수락 사례·반례 설계)
- **의존:** 기존 OCPN spec; charter identity 작업과 **병렬 가능·파일 충돌 시 Ashlar 조율**
- **비목표:** PM4Py OCPN과 수치 동치 증명; soundness 증명기 신규 구현

#### OCPM-P0-02 · Joint / Object-replay / Flattened 연산자 분리 계약

- **문제:** Flattened 평균을 joint 적합성으로 읽으면 shared event가 왜곡된다. **[이론]** OCPM 핵심.
- **근거:** `object_centric/conformance.py`; union OC-ALIGNMENT/REPLAY/FLATTENED. **[사실]**
- **수락 기준:**
  1. 세 경로의 `operator_id`(또는 동등)가 결과 JSON에서 **상호 구분**.
  2. 공개 API/가이드에 “합산 금지 / 별도 해석” 명시.
  3. 최소 1개 golden: 동일 OCEL·모델·동일 tip에서 joint vs flattened의 `operator_id`·핵심 수치가 **다름을 assert** (정성 서술만으로 끝내지 않음). 운영 KPI 가공·임의 fitness 수치 금지 — **비동일/부등 단언만**.
- **제안 소유:** Provenance · Fathom(golden·assert 설계)
- **의존:** 기존 conformance contracts
- **비목표:** 새 alignment 알고리즘 전면 교체; 두 경로 수치의 “올바른 차이량” 규범화

#### OCPM-P0-03 · OCDFG·EOG 빈도 분모 프로파일 버전 고정

- **문제:** event-pair / unique-object / total-object 분모가 섞이면 대시보드·실험이 비교 불가.
- **근거:** union OC-OCDFG·EVENT-GRAPH native; NATIVE_ANALYSIS 가이드. **[사실]**
- **수락 기준:**
  1. `docs/specifications/` 또는 user-guide에 분모별 정의표 + profile id.
  2. `discover_ocdfg` / EOG 관련 결과에 profile id·분모가 **직렬화**됨.
  3. Gesso용 주석 키·배지·툴팁 부록(구현 지시 아님). **채택 초안:** [`reviews/2026-09-27_Gesso_OCPM_VIS_배지_툴팁_카피_초안.md`](reviews/2026-09-27_Gesso_OCPM_VIS_배지_툴팁_카피_초안.md).  
     **최소 키:** `view_kind`, `view_kind_label`, `view_kind_definition`, `denominator_profile_id`, `denominator_label`, `denominator_tooltip`, `observational_badge`, `observational_tooltip`, `partial_badge`, `partial_tooltip`, `operator_id`, `operator_id_label`, `operator_tooltip`, `projection_receipt`, `projection_banner`, `layout_engine`, `layout_status`.  
     `denominator_profile_id` **실제 문자열**은 P0-03 명세가 우선(카피 초안 §2.1은 라벨·툴팁만).
  4. 화면 수락은 **OCPM-VIS-P0-02**와 교차참조 (분모·profile 배지).
- **제안 소유:** Provenance · Gesso(라벨·UX 의미) · Fathom(지표 비교 프로토콜)
- **의존:** 기존 OCDFGSpec; VIS-P0-02
- **비목표:** 신규 layout 엔진

#### OCPM-P0-04 · Object→Case projection 손실·공유이벤트 영수증 의무

- **문제:** 투영 없이 case KPI를 OC 진실로 쓰면 convergence/divergence를 숨긴다. **[이론]**
- **근거:** `case_projection.py`; PM-OCEL-004/OC-DATA-001 **partial**. **[사실]**
- **수락 기준:**
  1. 투영 결과(또는 receipt)에 source OCEL digest/id, 객체형, tie 정책, shared-event 그룹 요약이 **필수**.
  2. “암묵 XES/Case ← OCEL” 경로 없음 — charter와 동일 원칙, **추가**로 투영 API 문서 must.
  3. Schumpeter/Skill 후보 allowlist에 투영 없이 OC를 case fitness로 말하라는 항목 **없음** (문서 수준).
  4. **UX:** 투영 파생 시각화는 receipt 요약 배너 없이 case KPI로 제시하지 않는다 (**OCPM-VIS-P0-04**).
- **제안 소유:** Provenance · Fathom(누출·split 감사 지표) · Gesso(배너 의미)
- **의존:** REV projection metadata (charter 언급) — **충돌 시 charter 우선**; VIS-P0-04
- **비목표:** 투영을 기본값으로 만들기

#### OCPM-P0-05 · OCEL 2.x qualifier·객체 속성 이력 — **문서 표·정책만** (구현 강제 아님)

- **문제:** ingest는 있으나, 어떤 OC 연산이 qualifier/as-of 속성을 **실제로 소비**하는지 제품 표면이 흩어져 있으면 OCPM 차별점이 불투명.
- **근거:** OCEL 2.0 메타모델 **[이론]**; PIX constraints/enrichment/filtering/performance 코드 존재 **[사실]**; 행별 partial 혼재.
- **수락 기준 (문서 산출물):**
  1. “Qualifier·attribute-change를 읽는 연산” vs “무시하는 연산” **표 1장** (api/object_centric 기준, union 행 ID 교차 참조).
  2. 무시 경로에 대한 **정책 문구**만 동결: 후속 구현 시 `ignored_qualifiers`/`attribute_history_not_used`류 issue·spec 플래그를 쓸 수 있음 — **본 P0는 코드 개조를 수락 조건으로 두지 않음**.
  3. 표·정책이 공개 가이드/요구 부록으로 링크 가능.
- **제안 소유:** Provenance · Fathom(표 검증 샘플)
- **의존:** OCEL model; constraints V1 등
- **비목표 (굵게):** **전 연산 즉시 개조 금지**; 2.1 최종 표준 재인증; P0를 “전 연산이 qualifier를 읽도록 구현하라”로 해석 금지

#### OCPM-P0-A1 · Sequence→OC 의미 부록 (P0 부록 · Fathom must-for-DS)

> 대표님 강조 축. 상세 실험 프로토콜은 **OCPM-P1-11**·**P1-13**. 본 부록은 **오용 금지·용어 최소 계약**만 P0로 고정한다.

- **문제:** 선형 trace의 frequent sequence / episode / sequential pattern을 OCDFG·OCPN·OC 적합성처럼 읽으면 객체 동시성·공유 이벤트가 왜곡된다. **[이론]** + 대표님 지시 **[추론: 우선순위]**
- **수락 기준:**
  1. 1페이지 부록: 선형 sequence ≠ process model / OCDFG / OCPN (용어표). **부분순서·객체 동시성**이 선형 trace와 다름을 한 줄로 명시.
  2. PIX에 sequential-pattern 연산이 **없으면** `UNAVAILABLE` — 휴리스틱·자체 구현으로 PIX 결과인 양 보고 금지 (pix-first).
  3. 반례 ≥1: **공유 이벤트를 객체별 선형화하면** frequent pattern이 깨지거나 생기는 예 (문서·fixture 스키마; 가공 fitness 금지).
- **제안 소유:** **Fathom** · Provenance
- **비목표:** sequence mining 엔진을 PIX에 즉시 이식; PM4Py 패턴 연산 의존

### 5.1.1 화면 수락 기준 — OCPM-VIS-P0 (계산 P0와 병렬, Gesso)

> Ashlar 승인: 계산 JSON만 맞고 화면이 오해 유도하면 **제품 수락 불가**와 동일.  
> 상세 리뷰: [`reviews/2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md`](reviews/2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md).  
> 배지·툴팁 카피 초안(채택): [`reviews/2026-09-27_Gesso_OCPM_VIS_배지_툴팁_카피_초안.md`](reviews/2026-09-27_Gesso_OCPM_VIS_배지_툴팁_카피_초안.md).  
> Graphviz WASM · Chevron · `VisualizationDocument` **확장** (재발명·새 layout 엔진 금지). Casement FE 구현 지시 없음.

| ID | 제목 | 수락 기준 (요약) | 연결 |
| --- | --- | --- | --- |
| **OCPM-VIS-P0-01** | 뷰 정체성 크롬 | OCDFG/EOG/OCPN/Relation/Chevron/Conformance(연산자별)에 **뷰 종류 + 한 줄 정의** 상시 노출. Graphviz 배치만으로 뷰 종류 추론 금지 | IA |
| **OCPM-VIS-P0-02** | 분모·profile 배지 | 빈도 OC graph에 profile id·분모 라벨·툴팁(P0-03 키) 상시. 분모 전환 시 숫자와 배지 동시 변경 | P0-03 |
| **OCPM-VIS-P0-03** | Observational·Partial 배지 | OCPN·partial에 `observational`/`partial`/`unavailable` 배지. ok 패널에 실패 provenance를 근거처럼 붙이지 않음 | P0-01 |
| **OCPM-VIS-P0-04** | Projection 손실 배너 | 투영 파생 case 뷰에 source digest·객체형·tie·shared-event 요약 배너. receipt 없으면 권위 KPI 금지 | P0-04 |
| **OCPM-VIS-P0-05** | 연산자 분리 표시 | Joint/Object-replay/Flattened를 한 KPI 카드·sparkline에 합치지 않음. 패널 `operator_id` 배지 | P0-02 |
| **OCPM-VIS-P0-06** | 단위·미지 값 | `VisualMetric` 단위 범례; `None`/unknown을 0으로 칠하지 않음 | 시각화 계약 |
| **OCPM-VIS-P0-07** | 레이아웃 실패 노출 | Graphviz/native/elk 실패 시 자동 fallback 없이 오류 UI (GV-02와 동일 원칙) | Graphviz 요구 |

---

### 5.2 P1 — [should]

| ID | 제목 | 문제·근거 | 수락 기준 (요약) | 소유 |
| --- | --- | --- | --- | --- |
| OCPM-P1-01 | Object context 정의 동결 | OC-CONTEXT partial; OCPA context ≠ PIX binding-prefix | PIX-native 분모·termination 명세 + 예제 1 | Provenance · Fathom |
| OCPM-P1-02 | OPERA annotation·요약 통계 | OC-PERF-005/006 partial | activity/arc 빈도·참여 annotation 프로파일; 요약 통계 완전성 | Provenance · Fathom · Gesso(표시) |
| OCPM-P1-03 | Replay silent/flooding 정책 | OC-CONF-005 partial | 정책 enum·결과 필드·가이드 | Provenance |
| OCPM-P1-04 | Variant graph isomorphism | OC-EXEC-004/005 partial; 전수는 복잡도 폭발 **[추론]** | 동치 정의 + **P1-12 한도와 필수 결합**; 한도 초과 시 UNAVAILABLE (빈 성공 위장 금지) | Provenance · Fathom |
| OCPM-P1-05 | 필터 time/lifecycle/perf | OC-FILTER-002/005/006 partial | 세 필터의 명시 의미·closure | Provenance |
| OCPM-P1-06 | ET-OT/OTG graph conformance | PM-OCEL-024 partial | OCDFG와 대칭인 비교 프로파일 | Provenance · Gesso |
| OCPM-P1-07 | OCCN↔OCPN 변환 손실 보고 | MODEL-CONVERT partial | 방향별 loss report 필수 필드 | Provenance |
| OCPM-P1-08 | Lifecycle qualifier enrichment | PM-OCEL-009 partial | first/last E2O 마크 완전성·충돌 정책 | Provenance |
| OCPM-P1-09 | OCEL 2.1 최종본 추적 | pre4 고정 **[사실]** | 최종 PDF 대비 diff 체크리스트 (구현 전 Ashlar 승인) | Provenance |
| OCPM-P1-10 | OC 시각화 의미 패키지 (인덱스) | chevron/Graphviz 존재 **[사실]** | **OCPM-VIS-P0-01…07 / VIS-P1-01…07로 분해·교차참조**. 한 줄 소유 선언만으로 수락 완료로 치지 않음 | **Gesso** · Provenance |
| OCPM-P1-11 | Sequence→OC 실험·반례 프로토콜 | P0-A1 용어 계약을 실험으로 확장; Fathom DS must | (1) 대상 연산·로그 타입 (2) golden·반례(공유이벤트 선형화 포함) (3) PIX vs exploratory 라벨 (4) 표본 한도 (5) UNAVAILABLE 조건 — 1페이지+ | **Fathom** · Provenance |
| OCPM-P1-12 | 복잡도·예산·UNAVAILABLE 탈출표 | OCPN discovery / joint align / variant iso; §7 대규모 성능 미측정 **[알 수 없음]** | 입력 파라미터(|E|,|O|,types,E2O)·한도·초과 시 UNAVAILABLE/PARTIAL·부분결과 위장 금지 표. **P1-04와 묶음**. 한도 초과 fixture에서 성공+빈결과 없음 | **Fathom** · Provenance |
| OCPM-P1-13 | DS 실험·지표·메타모픽 프로토콜 | 분모 혼동·fixture 미핀 위험 | 동일 분모 profile만 OCDFG/EOG 비교; 고정 golden OCEL 목록; 순열→동일 digest; object-type ablation은 **명세된 단조(또는 문서화된 예외)**; 근사 경로 시 seed·n·누락 건수. charter DS PASS 정신 | **Fathom** · Provenance |

#### OCPM-VIS-P1 — [should] (Gesso, P1-10 분해)

| ID | 제목 | 수락 기준 (요약) |
| --- | --- | --- |
| **OCPM-VIS-P1-01** | OCPM 뷰 맵(IA) | Discovery→Execution→Model→Conformance→Performance→Relations 권장 경로 1장. 같은 `source_digest` 교차 링크 |
| **OCPM-VIS-P1-02** | 대용량 가독성 | 객체형 접기, edge weight **표시** 필터, 밀도 경고 (계산 삭제 아님) |
| **OCPM-VIS-P1-03** | OPERA/성능 주석 가독성 | annotation과 요약 통계 분리; 평균의 분자·분모·unknown 노출 (P1-02 정합) |
| **OCPM-VIS-P1-04** | ET-OT/OTG 대칭 범례 | OCDFG 대칭 비교 프로파일 범례·이중 부호화 (P1-06) |
| **OCPM-VIS-P1-05** | OCCN↔OCPN 변환 손실 UI | 방향별 loss report 배너/표 (P1-07) |
| **OCPM-VIS-P1-06** | 접근성 | 색만으로 구분 금지; 키보드 선택; 배지 텍스트 대체; Neutral Chevron 기본 |
| **OCPM-VIS-P1-07** | 금지 카피 체크리스트 | sound OCPN / 전체 fitness 보장 / flattened=joint / 슬롯=시간 / Graphviz=병목 금지 |

---

### 5.3 P2 — [could]

| ID | 제목 | 비고 |
| --- | --- | --- |
| OCPM-P2-01 | OC predictive feature/dataset 확장 | FEATURE-DATASET partial 잔여 |
| OCPM-P2-02 | Action impact 고도화 | IMPACT partial; **실행은 Schumpeter** |
| OCPM-P2-03 | Revisable OC stream | 존재하나 제품 우선순위 낮음 **[추론]** |
| OCPM-P2-04 | intelligence/lineage stub | 비범위; 별도 기획 |
| OCPM-P2-05 | reference_replacement_verified 캠페인 | charter/union 트랙과 조율 |

---

## 6. 제안 작업 분할

| 역할 | OCPM 추가 요구에서의 책임 | 비고 |
| --- | --- | --- |
| **Provenance (PI)** | 본 백로그 의미론·수락 기준·표준/문헌 정합; OCPN/conformance/projection/qualifier 계약 | Lead |
| **Fathom** | **알고리즘 서포트**: **P0-A1·P0-02·P1-11·P1-12·P1-13** 소유/공동 — sequence→OC 의미·실험, 복잡도 한도표, joint≠flattened assert, 분모·메타모픽·fixture | charter DS 축과 정합; **구현 지시 아님** |
| **Gesso** | **시각화 요구·UX 전담**: **OCPM-VIS-P0-01…07 · VIS-P1-01…07** (뷰 크롬·분모/연산자/observational 배지·projection 배너·범례·a11y·금지 카피). 리뷰·카피: `reviews/2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md`, `reviews/2026-09-27_Gesso_OCPM_VIS_배지_툴팁_카피_초안.md` | Casement FE는 문서 최종 승인·docs-only PR 이후 |
| **Ashlar** | 우선순위·Vera/팀 충돌 조율·승인 | |
| **Vera** | charter P0 identity; 본 문서 P0와 **경로 겹치면 Ashlar 선보고** | 본 문서가 Vera 작업을 재정의하지 않음 |
| **Keel (BE)** | **범위 확대 시** — `pix.api`/결과 문서 소비자 계약이 Schumpeter 밖으로 커질 때만 | 현재 문서에 구현 지시 없음 |
| **Coffer (DB)** | **범위 확대 시** — 결과·digest 영속 스키마가 제품 저장 요구로 커질 때만 | 현재 문서에 구현 지시 없음 |
| **Casement** | 일반 FE; OC 시각 의미는 Gesso 우선 | |
| **Schumpeter** | Skill allowlist·라이브 emission; PIX 계산 흉내 금지 | Out of PIX 구현 |

### 6.1 Fathom 소유 ID 연결

| ID | Fathom 역할 |
| --- | --- |
| **OCPM-P0-A1** | Sequence≠OCDFG 용어·UNAVAILABLE·공유이벤트 선형화 반례 (P0 부록) |
| **OCPM-P0-02** | joint vs flattened 비동일 assert golden |
| **OCPM-P1-11** | Sequence→OC 실험·반례 프로토콜 전문 |
| **OCPM-P1-12** | OCPN/joint/variant iso 복잡도·예산·UNAVAILABLE 표 (**P1-04 묶음**) |
| **OCPM-P1-13** | 분모·fixture·메타모픽·seed 프로토콜 |

### 6.2 Fathom 체크 — Sequence → PM / DS 프로토콜

문서 합의 후 Fathom이 채울 체크(구현 지시 아님):

- [ ] P0-A1 용어표 + 공유이벤트 선형화 반례 1
- [ ] P1-11: sequence/pattern → PIX Case/OC 연산 매핑·exploratory 라벨
- [ ] P1-12: |E|·|O|·types·E2O 한도표 + P1-04 iso 한도 결합
- [ ] P0-02: tip+fixture에서 joint≠flattened assert
- [ ] P1-13: 고정 fixture 핀·순열 digest·ablation·근사 seed
- [ ] charter DS 축·Vera P0와 ID/경로 충돌 없음

### 6.3 Gesso 소유 ID 연결

| ID | Gesso 역할 |
| --- | --- |
| **OCPM-VIS-P0-01…07** | 화면 must — 정체성·분모·observational·projection·연산자·단위·레이아웃 실패 |
| **OCPM-VIS-P1-01…07** | 화면 should — IA·대용량·OPERA·범례·loss UI·a11y·금지 카피 |
| **OCPM-P1-10** | 위 VIS-* 인덱스 (단독 수락 기준 아님) |
| **OCPM-P0-03/04** | 부록 키·projection 배너 UX 한 줄 공동 |

---

## 7. 리스크·열린 질문

| 항목 | 종류 | 내용 |
| --- | --- | --- |
| Charter 중복 | 리스크 | identity/projection 문구가 Vera P0와 겹칠 수 있음 → **charter 우선**, 본 문서는 OC 제품 해석만 |
| OCPN 마케팅 과장 | 리스크 | observational을 sound로 오인 |
| 분모 혼동 | 리스크 | OCDFG/성능 KPI 비교 불가 |
| Flattened≠Joint | 리스크 | 공유 이벤트 이중 계산 |
| 2.1 pre4 vs 최종 | 열린 질문 | 최종 PDF 일정·breaking change? **[알 수 없음]** |
| 대규모 성능 | 열린 질문 | 본 pass에서 벤치 미실행 **[알 수 없음]** |
| Skill pin 범위 | 열린 질문 | A.7 allowlist에 P0-03/05 필드 포함 여부 → Ashlar·Schumpeter |
| Keel/Coffer 시기 | 열린 질문 | 결과 envelope가 Hub 저장 계약이 되는 시점 |

---

## 8. 출처

### 8.1 저장소 (로컬)

- `/workspace/PIX` (`feat/ocel-readers-v0.2.0` @ `8a66984`)
- `README.md`, `pyproject.toml`
- `docs/specifications/PIX_OCPN_DISCOVERY_V1.md`, `PIX_OCEL_CANONICAL_V1.md`, …
- `docs/requirements/2026-09-15_PIX_NATIVE_MINING_UNION.md`
- `docs/requirements/union-2026-09-15/OBJECT_CENTRIC_COVERAGE.md`, `implementation_registry.json`
- `docs/design/2026-09-12-import-v050.md`
- `docs/user-guide/NATIVE_*`, `VISUALIZATION_GUIDE.md`, `OCEL_READING_GUIDE.md`
- `src/pix/api.py`, `compute/{ocdfg,ocpn_discovery,object_conformance,object_context,…}.py`, `object_centric/*`
- `docs/audits/ALGORITHM_COMPLETENESS_REVIEW_CHARTER.md` (in-repo 포인터)
- `docs/requirements/reviews/2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md`
- `/workspace/PIX-audits/ALGORITHM_COMPLETENESS_REVIEW_CHARTER_MERGED.md`, `PI_FOLLOWUP_SECTION_FOR_CHARTER.md`
- `/workspace/handoff-docs/ASHLAR_DEVTEAM_BASELINE_2026-09-26.md`
- `/workspace/handoff-docs/ALGORITHM_COMPLETENESS_REVIEW_CHARTER.md`

### 8.2 외부 URL

- https://www.ocel-standard.org/specification/overview/
- https://ocel-standard.org/2.0/ocel20_specification.pdf
- https://www.ocel-standard.org/2.1/ocel20_specification.pdf
- https://www.ocel-standard.org/specification/formats/csv/
- https://www.ocel-standard.org/specification/formats/bundled/
- https://www.vdaalst.com/publications/p1108.pdf (OCPN discovery)
- https://export.arxiv.org/pdf/2204.10662v2.pdf (OPerA)
- https://github.com/ocpm/ocpa (참조 라이브러리 — 의존 제안 아님)
- https://processintelligence.solutions/pm4py/api/api/pm4py.ocel.html (갭 참조)

---

## 9. 변경 이력

| 시각 (KST) | 내용 |
| --- | --- |
| 2026-09-27 21:31 | 초안. charter 분리, P0–P2, Fathom=알고리즘 서포트, Gesso=시각화·UX, Keel/Coffer=범위 확대 시 |
| 2026-09-27 21:33 | Ashlar 1차 리뷰 반영: charter in-repo 이중 링크, OCPM-P1-11·§6.1 sequence→PM 프로토콜. docs-only PR은 Fathom/Gesso 합류 후 |
| 2026-09-27 21:34 | Fathom DS + Ashlar must 반영: P0-A1 Sequence 부록, P0-02 비동일 assert, P0-05 문서-only 강조, P1-11/12/13·§6.1–6.2 ID 연결. Gesso 대기 후 최종 승인·docs-only PR |
| 2026-09-27 21:35 | Gesso VIS + Ashlar 최종 조건: VIS-P0-01…07 must·VIS-P1-01…07 should, §1.2·P0-03/04·P1-10·§6.3 반영. Fathom 잔여 재확인. 최종 승인 대기 → docs-only PR |
| 2026-09-27 21:36 | Fathom 선택 보강: P0-A1 부분순서/동시성 한 줄, P1-13 ablation 명세된 단조(또는 문서화 예외). 최종 승인 요청 |
| 2026-09-27 21:37 | Gesso 배지·툴팁 카피 초안을 P0-03 부록으로 채택·링크. VIS must 본문 편입 재확인. Ashlar 최종 승인 재요청 |
