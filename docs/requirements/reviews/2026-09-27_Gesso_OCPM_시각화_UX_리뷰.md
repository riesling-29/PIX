# Gesso UX 리뷰 — OCPM 추가개발 요구사항 (시각화)

| 항목 | 내용 |
| --- | --- |
| 대상 | [`../OCPM_추가개발_요구사항.md`](../OCPM_추가개발_요구사항.md) |
| tip | `feat/ocel-readers-v0.2.0` @ `8a66984` |
| 작성 | Gesso (UX/UI) |
| 시각 (KST) | 2026-09-27 21:33 |
| 독자 | Provenance · Ashlar · 대표님 |
| 성격 | **요구·UX 보완** (FE/Casement 구현 지시 없음) |
| 정합 | Graphviz WASM 기본 배치 · Chevron · `VisualizationDocument` 계약 유지 |

### 참조한 기존 경로 (재발명하지 않음)

- `docs/design/2026-09-15-visualization-contract.md`
- `docs/requirements/2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md`
- `docs/requirements/2026-09-15_PIX_VISUALIZATION_UNION.md` (V-OC-01…08)
- `docs/user-guide/VISUALIZATION_GUIDE.md`

---

## 1. 총평

초안의 **계산·계약 P0(OCPN observational, joint/flattened 분리, 분모 profile, projection receipt, qualifier 지원 선언)** 는 시각화 의미의 토대로 충분하다.  
다만 **화면에 어떻게 오해 없이 나타나는지**는 아직 얇다.

- **충분:** P0-01~05가 “무엇을 숨기면 안 되는지”를 계산 결과 쪽으로 못 박은 점; P1-10이 Gesso 소유로 명시된 점; Graphviz/Chevron 기존 계약이 ID·단위·partial·공유사건 복제를 이미 금지하는 점.
- **부족:** 뷰 간 혼동(OCDFG↔EOG↔OCPN↔flattened), 배지·범례·배너 IA, projection 손실의 **화면 표면**, 접근성, 대용량 가독성의 must/should가 P1-10 한 줄에 압축됨.
- **방향:** 기존 `VisualizationDocument` / Graphviz WASM / Neutral Chevron을 **확장 요구**로 다루고, 새 layout 엔진·FE 일정은 비범위로 둔다.

---

## 2. 뷰 의미 — UX 충분성 판정

### 2.1 OCDFG

| 판정 | 이유 |
| --- | --- |
| **부분 충분** | V-OC-01·가이드에 type별 parallel edge, `event_pairs` / `objects` / `occurrences` 삼분모가 이미 있다. P0-03이 profile id 직렬화를 요구한다. |
| **남는 UX 갭** | 화면에 지금 어떤 분모가 켜져 있는지 **상시 배지+툴팁** 요구가 P0-03 부록·P1-10에만 암시되어 있다. 삼분모를 같은 숫자 슬롯에 바꿔 끼우면 대시보드 비교가 깨지므로, 전환 UI는 **라벨 교체 + 활성 profile 고정 표시**가 must다. |

**UX 카피 원칙 (제안):**  
“Event pairs = 서로 다른 이벤트 쌍 수 / Objects = 참여 객체 수 / Occurrences = (event, object[, qualifier]) 관측 수. 같은 shared event를 객체 수만큼 세지 않는다.”

### 2.2 EOG

| 판정 | 이유 |
| --- | --- |
| **문서상 Have, UX는 혼동 위험** | 초안 §2.3·갭표는 EOG≠OCDFG를 인정한다. 화면에서 둘 다 “객체 중심 그래프”로 보이면 해석이 섞인다. |
| **남는 UX 갭** | 뷰 크롬에 **뷰 종류 ID + 한 줄 정의**가 없다. EOG는 객체별 선후행, OCDFG는 타입/활동 집계 흐름임을 전환·제목·범례에서 고정해야 한다. |

### 2.3 OCPN (관측적)

| 판정 | 이유 |
| --- | --- |
| **계약은 P0-01로 잡힘, 표시는 미비** | observational cardinality / joint guarantee 필드가 나와도, Graphviz 그림만 보면 “완성된 Petri net”으로 읽히기 쉽다. |
| **남는 UX 갭** | 문서·패널 status와 별도로 **`observational` 배지(상시)** , soundness 비주장 문구, silent/marking/cardinality 범례가 must. 레이아웃 좌표를 병목·인과 증명으로 읽게 하는 카피 금지. |

### 2.4 Projection 손실 라벨

| 판정 | 이유 |
| --- | --- |
| **API receipt(P0-04)만으로는 UX 불충분** | 영수증 필드가 있어도 case KPI 화면에 안 붙으면 convergence/divergence가 다시 숨는다. |
| **남는 UX 갭** | 투영 파생 뷰에는 **지속 배너**(닫아도 ‘근거 숨김’이 되지 않게 재진입 시 재표시) + shared-event 요약 + tie 정책 + source OCEL digest 링크성 표시가 must. receipt 없으면 해당 뷰를 권위 있는 case KPI로 제시 금지. |

### 2.5 Chevron / variant

| 판정 | 이유 |
| --- | --- |
| **기존 경로로 충분(의미)** | 슬롯≠시간, shared event 단일 ID, Neutral 기본, unlaned 표 분리가 이미 있다. |
| **남는 UX 갭** | OCPM 여정에서 chevron이 “실행·variant” 단계임을 IA에 명시; Classic 색만으로 객체형 구분하는 경로는 a11y should에서 Neutral·텍스트 병행을 기본 권고. |

### 2.6 Conformance (joint / object-replay / flattened)

| 판정 | 이유 |
| --- | --- |
| **P0-02 연산자 분리는 필수, 화면 규칙 필요** | 동일 카드·동일 축에 세 수치를 올리면 UX가 계약을 깨뜨린다. |
| **남는 UX 갭** | 패널마다 `operator_id` 배지; 합산·평균 금지 카피; flattened 뷰에 “OC 진실 아님(공유 이벤트 왜곡 가능)” 경고 should→P0에 가까운 must. |

---

## 3. Gesso 전담 — 보완 must / should / 비범위

기존 **OCPM-P1-10**은 유지하되, 아래를 **세분 ID**로 백로그에 편입할 것을 제안한다. (구현은 Casement 이후; 본 문서는 요구만.)

### 3.1 [must] — P0에 붙이거나 P1-10을 승격·분해

| ID | 제목 | 수락 기준 (요약) | 연결 |
| --- | --- | --- | --- |
| **OCPM-VIS-P0-01** | 뷰 정체성 크롬 | OCDFG / EOG / OCPN / Relation / Chevron / Conformance(연산자별) 화면에 **뷰 종류 + 한 줄 정의**가 상시 노출. Graphviz 배치만으로 뷰 종류를 추론하지 않음. | IA |
| **OCPM-VIS-P0-02** | 분모·profile 배지 | 빈도 있는 OC graph에 profile id·분모 라벨·툴팁 문자열(P0-03 부록 키) 상시 표시. 분모 전환 시 숫자와 배지가 함께 바뀜. | P0-03 |
| **OCPM-VIS-P0-03** | Observational·Partial 배지 | OCPN·partial 결과에 `observational` / `partial` / `unavailable` 배지. `ok` 패널에 실패 입력 provenance를 근거처럼 붙이지 않음(기존 Inspector 계약 재확인). | P0-01, 시각화 계약 |
| **OCPM-VIS-P0-04** | Projection 손실 배너 | 투영 파생 case 뷰에 source digest·객체형·tie 정책·shared-event 요약 배너 필수. receipt 부재 시 권위 KPI 제시 금지. | P0-04 |
| **OCPM-VIS-P0-05** | 연산자 분리 표시 | Joint / Object-replay / Flattened를 한 KPI 카드·한 sparkline에 합치지 않음. 패널 단위 `operator_id` 배지. | P0-02 |
| **OCPM-VIS-P0-06** | 단위·미지 값 | `VisualMetric` 단위 범례 필수; `None`/unknown을 0으로 칠하지 않음(계약 재진술 + 화면 범례). | 시각화 계약 |
| **OCPM-VIS-P0-07** | 레이아웃 실패 노출 | Graphviz/native/elk 실패 시 자동 fallback 없이 오류 상태 UI(기존 GV-02와 동일 원칙을 UX 수락으로 명시). | Graphviz 요구 |

### 3.2 [should] — P1

| ID | 제목 | 수락 기준 (요약) |
| --- | --- | --- |
| **OCPM-VIS-P1-01** | OCPM 뷰 맵(IA) | Discovery(OCDFG) → Execution(EOG/Chevron) → Model(OCPN) → Conformance(연산자별) → Performance → Relations 권장 경로 1장. 같은 `source_digest` 교차 링크. |
| **OCPM-VIS-P1-02** | 대용량 가독성 | 객체형 접기, edge weight 임계 필터(계산 삭제 아님·표시만), 밀도 경고. Graphviz 품질 보장은 주장하지 않음. |
| **OCPM-VIS-P1-03** | OPERA/성능 주석 가독성 | activity/arc annotation과 요약 통계를 모델 그림·별도 표로 분리 표기(P1-02와 정합). 평균의 분자·분모·unknown 노출. |
| **OCPM-VIS-P1-04** | ET-OT/OTG 대칭 범례 | OCDFG와 대칭인 비교 프로파일의 범례·색/무채 이중 부호화(P1-06). |
| **OCPM-VIS-P1-05** | OCCN↔OCPN 변환 손실 UI | 방향별 loss report 필드를 배너/표로 표시(P1-07). |
| **OCPM-VIS-P1-06** | 접근성 | 색만으로 객체형·상태 구분 금지(텍스트/패턴 병행). 키보드로 노드·엣지·chevron 선택. 배지·범례에 텍스트 대체. Neutral Chevron 기본 권고 유지. |
| **OCPM-VIS-P1-07** | 카피 체크리스트 | “sound OCPN”, “전체 fitness 보장”, “flattened = joint”, “슬롯 = 시간”, “Graphviz가 병목을 찾음” 금지 문구 목록(Skill/가이드/UI 공통). |

### 3.3 비범위 (Gesso 이번 패스)

| 항목 | 이유 |
| --- | --- |
| Casement FE 일정·컴포넌트 구현 | Ashlar 승인 후 |
| 새 layout 엔진(Cytoscape/Sigma 등) 도입 | 기존 Graphviz WASM 경로 유지 |
| 계산 알고리즘·operator 수치 변경 | Provenance/Fathom |
| Charter/Vera identity UI | 별도 트랙 |
| Schumpeter Skill 실행 화면 | Schumpeter 소유 |

---

## 4. 초안 문구에 대한 구체 수정 제안

1. **§1.2** “시각화에 넘길 OC 뷰 의미·손실 라벨” →  
   “**뷰 정체성·분모/연산자/observational 배지·projection 손실 배너·범례/접근성**을 포함한 표시 의미 (FE 지시 아님)” 로 구체화.
2. **OCPM-P0-03** 수락 3항 “Gesso용 주석 키 부록” →  
   부록에 최소 키: `view_kind`, `denominator_profile_id`, `denominator_label`, `denominator_tooltip`, `observational_badge`, `partial_badge`, `operator_id_label`.
3. **OCPM-P0-04** 수락에 UX 한 줄 추가:  
   “투영 파생 시각화는 receipt 요약 배너 없이 case KPI로 제시하지 않는다.”
4. **OCPM-P1-10**을 위 VIS-P0/P1로 **분해·교차참조** (한 줄 소유 선언만으로 수락 기준이 되지 않게).
5. **§6 Gesso 행**에 VIS-P0-01…07 / VIS-P1-01…07 링크 추가.

---

## 5. 오해 방지 카피 (초안, 한국어)

| 상황 | 권장 문구 |
| --- | --- |
| OCPN | “관측 구간·수용 witness 기준 모델입니다. Joint soundness나 규범적 cardinality를 보장하지 않습니다.” |
| Flattened | “Case로 펼친 재생입니다. 공유 이벤트 때문에 Object-centric joint 적합성과 숫자가 다를 수 있습니다.” |
| Projection | “OCEL에서 투영된 Case 뷰입니다. 손실·공유 이벤트 요약이 아래에 있습니다. OC 원본 진실이 아닙니다.” |
| Chevron 슬롯 | “가로(세로) 칸은 선행관계 단계입니다. 대기·처리 시간이 아닙니다.” |
| Graphviz | “배치는 읽기 위한 좌표입니다. 병목이나 인과를 새로 계산한 결과가 아닙니다.” |
| OCDFG 분모 | 활성 profile 이름을 숫자 옆에 항상 표기. |

---

## 6. 보고·다음 액션

| 누구에게 | 무엇 |
| --- | --- |
| **Provenance** | 본 리뷰 반영해 초안 §1.2·P0-03/04·P1-10 및 VIS-* ID 편입 여부 결정 |
| **Ashlar** | 시각화 must 승격(VIS-P0) 우선순위·Casement 착수 시점 조율 |
| **Gesso** | Provenance가 부록 키 초안을 열면 툴팁/배지 카피 확정 패스 |
| **Casement** | 구현 착수 전 본 문서 + 시각화 계약을 입력으로 받음 (지금은 대기) |

**결론:** 뷰 의미의 **계산 쪽 뼈대는 초안으로 충분**하다. Gesso 전담으로 빠진 것은 **정체성 크롬·분모/연산자/observational 배지·projection 손실 배너·금지 카피·접근성**이며, 이를 VIS-P0/P1로 명시할 것을 요청한다.

---

## 7. Ashlar 재요청 재확인 (2026-09-27 21:34 KST)

대상 tip 재확인: `OCPM_추가개발_요구사항.md` 및 사본 `wmc-reports/PIX_OCPM_추가개발_요구사항.md` (동일, 361행).

Ashlar 1차 반영분(OCPM-P1-11 · §6.1 sequence→PM)은 **Fathom 실험 프로토콜**이며 시각화 must/should를 바꾸지 않는다.  
§1.2·P0-03/04·P1-10·§6 Gesso 행은 초안과 동일 → **본 리뷰 §1–6 결론 유지**. VIS-P0/P1 편입만 요청.

**Ashlar에 올리는 시각화 코멘트 (요약):**

1. **승인 권고(계산 P0):** P0-01…05는 시각화 의미의 전제로 유지.
2. **문서 보완 must:** VIS-P0-01…07을 백로그에 명시(또는 P1-10을 동 수준으로 분해·수락 기준화). 특히 projection 손실 **화면 배너**(P0-04 UX 한 줄), 분모/observational/operator 배지.
3. **should:** VIS-P1 IA 맵·대용량 가독성·OPERA 표시·a11y·금지 카피.
4. **비범위 확인:** Casement FE·새 layout 엔진·계산 변경 없음. Graphviz WASM·Chevron·`VisualizationDocument` 확장.
5. **P1-11:** 시각화 비범위. exploratory 라벨이 화면에 섞일 경우만 추후 Gesso 카피 점검(지금은 Fathom 동결 후).
