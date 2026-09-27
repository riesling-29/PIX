# Gesso 초안 — OCPM 시각화 주석 키·배지·툴팁 카피

| 항목 | 내용 |
| --- | --- |
| 작성 | Gesso (UX/UI) |
| 시각 (KST) | 2026-09-27 21:34 |
| 근거 | Ashlar 판정: VIS-P0-01…07 must 편입 승인; Provenance 부록 키 요청 |
| 상태 | **카피 초안** — Provenance가 부록 키를 본문에 열면 본 문서로 확정 패스 |
| 비범위 | Casement FE 구현·문자열 i18n 프레임워크·계산 필드 스키마 변경 |

관련: [`2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md`](./2026-09-27_Gesso_OCPM_시각화_UX_리뷰.md), [`../OCPM_추가개발_요구사항.md`](../OCPM_추가개발_요구사항.md)

---

## 1. 주석 키 목록 (P0-03 부록 후보)

JSON/`VisualField`·배지 슬롯에 쓸 **안정 키**. 값은 아래 카피 또는 Provenance가 고정한 profile id.

| key | 타입(제안) | 필수(VIS) | 의미 |
| --- | --- | --- | --- |
| `view_kind` | enum string | must | 뷰 정체성. 아래 §2 |
| `view_kind_label` | string | must | 화면 제목 옆 짧은 한글 라벨 |
| `view_kind_definition` | string | must | 한 줄 정의(상시 크롬) |
| `denominator_profile_id` | string | must (빈도 graph) | P0-03 profile id |
| `denominator_label` | string | must (빈도 graph) | 숫자 옆 짧은 라벨 |
| `denominator_tooltip` | string | must (빈도 graph) | 툴팁 본문 |
| `observational_badge` | bool or enum | must (OCPN 등) | 관측적 모델 표시 |
| `observational_tooltip` | string | must when badge | |
| `partial_badge` | enum: `ok`/`partial`/`unavailable`/`error` | must | 문서·패널 표시 상태 |
| `partial_tooltip` | string | must when not ok | |
| `operator_id` | string | must (conformance) | joint / object_replay / flattened 등 |
| `operator_id_label` | string | must (conformance) | |
| `operator_tooltip` | string | must (conformance) | |
| `projection_receipt` | object/ref | must (투영 파생) | P0-04 receipt |
| `projection_banner` | string | must when receipt | 배너 본문 |
| `layout_engine` | string | should | `graphviz`/`native`/`elk` |
| `layout_status` | enum | must on failure | 실패 시 silent fallback 금지 |

### 1.1 `view_kind` enum (초안)

| 값 | 한글 라벨 | 한 줄 정의 |
| --- | --- | --- |
| `ocdfg` | OCDFG | 객체형·활동 사이 집계 흐름. 분모(profile)에 따라 숫자 의미가 달라집니다. |
| `eog` | EOG | 객체별 사건 선후행 그래프. OCDFG와 같은 그림이 아닙니다. |
| `ocpn` | OCPN | 객체 중심 Petri net(관측·수용 witness). Joint soundness를 보장하지 않습니다. |
| `relation_graph` | 관계 그래프 | 객체 상호작용 등 관계·witness. 발견 흐름(OCDFG)과 별도입니다. |
| `chevron` | Variant Chevron | 객체 instance 행과 공유 사건. 칸 폭은 시간이 아니라 선행 단계입니다. |
| `conformance_joint` | Joint 적합성 | 공유 이벤트를 한 번으로 두는 object-centric 정렬/재생. |
| `conformance_object_replay` | Object token replay | 객체 토큰 재생. Joint·Flattened와 같은 연산이 아닙니다. |
| `conformance_flattened` | Flattened 재생 | Case로 펼친 재생. Joint 적합성과 숫자가 다를 수 있습니다. |
| `opera` | OPERA/성능 주석 | 모델 위 성능 주석. 배치는 병목 증명이 아닙니다. |
| `projection_case` | 투영 Case 뷰 | OCEL→Case 투영 결과. OC 원본 진실이 아닙니다. |

---

## 2. 배지·툴팁 카피 (한국어, 확정 후보)

### 2.1 분모 (OCDFG 등)

| profile 예시 id | `denominator_label` | `denominator_tooltip` |
| --- | --- | --- |
| `event_pairs` | 이벤트 쌍 | 서로 다른 이벤트 쌍의 수입니다. 같은 공유 사건을 객체 수만큼 세지 않습니다. |
| `objects` | 객체 수 | 해당 관계에 참여한 고유 객체 수입니다. |
| `occurrences` | 관측 수 | (사건, 객체[, qualifier]) 관측 횟수입니다. qualifier가 여럿이어도 unique event 수를 늘리지 않는 정의는 연산 계약을 따릅니다. |

*실제 profile id 문자열은 Provenance P0-03 명세가 우선. 위는 라벨·툴팁 카피만.*

### 2.2 Observational / Partial

| 키 | 배지 짧은 텍스트 | 툴팁 |
| --- | --- | --- |
| observational | 관측적 | 관측 구간·수용 witness 기준입니다. Joint soundness나 규범적 cardinality를 보장하지 않습니다. |
| partial | 부분 | 일부만 계산·표시되었습니다. 빈 칸을 0으로 읽지 마세요. |
| unavailable | 불가 | 이 조건에서는 결과를 제공할 수 없습니다. |
| error | 오류 | 시각화 또는 배치에 실패했습니다. 다른 엔진으로 조용히 바꾸지 않습니다. |

### 2.3 연산자

| operator | 라벨 | 툴팁 |
| --- | --- | --- |
| joint | Joint | 공유 이벤트를 한 번으로 두는 object-centric 적합성입니다. Flattened 평균과 합산하지 마세요. |
| object_replay | Object replay | 객체 토큰 재생입니다. Joint·Flattened와 별도 연산입니다. |
| flattened | Flattened | Case로 펼친 재생입니다. 공유 이벤트 때문에 Joint와 숫자가 다를 수 있습니다. |

### 2.4 Projection 배너

기본 템플릿:

> OCEL에서 투영된 Case 뷰입니다. 원본 `{source_digest_short}` · 객체형 `{object_types}` · tie 정책 `{tie_policy}` · 공유 이벤트 그룹 `{shared_event_groups}`. OC 원본 진실이 아닙니다.

receipt 없음:

> 투영 영수증이 없어 이 화면을 Case KPI로 제시할 수 없습니다.

### 2.5 Chevron / Graphviz (상시 도움말)

| 상황 | 문구 |
| --- | --- |
| Chevron 축 | 가로(세로) 칸은 선행관계 단계입니다. 대기·처리 시간이 아닙니다. |
| Shared event 선택 | 같은 사건 ID를 여러 객체 행에 보여 줍니다. 사건이 여러 번 일어난 것이 아닙니다. |
| Graphviz | 배치는 읽기 위한 좌표입니다. 병목이나 인과를 새로 계산한 결과가 아닙니다. |

### 2.6 금지 카피 (UI·가이드·Skill 공통 체크)

다음에 해당하는 표현 **사용 금지**:

- sound OCPN / 전체 fitness 보장
- flattened = joint (또는 동일시)
- 슬롯 = 시간 / duration
- Graphviz가 병목을 찾음
- 투영 Case = OC 진실
- unknown/부분 결과를 0으로 채움

---

## 3. 확정 패스 체크리스트 (키 초안 open 시)

- [ ] Provenance 부록의 key 이름·enum이 §1과 충돌 없는지 diff
- [ ] profile id 실제 문자열로 §2.1 라벨 재매핑
- [ ] OCPN 필드명(`observational_cardinality` 등)과 배지 트리거 조건 일치
- [ ] projection receipt 필드 → 배너 플레이스홀더 매핑
- [ ] Ashlar에 확정본 경로 보고 · Casement 입력용으로 동결

---

## 4. 변경 이력

| 시각 (KST) | 내용 |
| --- | --- |
| 2026-09-27 21:34 | Ashlar VIS-P0 승인 후 카피·키 초안 선제 작성 |

---

## 5. 확정 패스 (2026-09-27 21:35 KST) — 본문 반영분 대조

대상: `OCPM_추가개발_요구사항.md` 21:35 이력 (VIS-P0 §5.1.1 · P0-03 최소 키 · P0-04 UX · P1-10 · §6.3).

| 체크 | 결과 |
| --- | --- |
| VIS-P0-01…07 본문 편입 | **일치** (§5.1.1) |
| VIS-P1-01…07 should | **일치** |
| P0-03 최소 키 ⊆ 본 초안 §1 | **일치** (`view_kind`, `denominator_profile_id`, `denominator_label`, `denominator_tooltip`, `observational_badge`, `partial_badge`, `operator_id_label`) |
| P0-04 UX 배너 한 줄 | **일치** (VIS-P0-04) |
| Graphviz/Chevron 확장·Casement 비범위 | **일치** |
| §2–2.6 카피 | **확정 후보 유지** — profile id 실문자열이 P0-03 명세에 고정되면 §2.1 라벨만 재매핑 |

### 5.1 부록에 넣으면 좋은 확장 키 (must 최소 밖 · should)

본문 최소 키만으로도 VIS-P0 수락은 가능. Casement 입력 완결을 위해 부록에 **권장 추가**:

- `view_kind_label`, `view_kind_definition` (VIS-P0-01 크롬)
- `operator_id` (P0-02와 동일 필드; 라벨만 있으면 id 누락 시 배지 바인딩 약함)
- `operator_tooltip`, `observational_tooltip`, `partial_tooltip`
- `projection_banner` (또는 receipt→배너 매핑 표)
- `layout_status` (VIS-P0-07)

### 5.2 Gesso 판정

**카피 확정 패스 완료(초안 동결).** Ashlar 문서 최종 승인·docs-only PR 이후 Casement 입력으로 사용. profile id 실값이 나중에 바뀌면 §2.1만 개정.
