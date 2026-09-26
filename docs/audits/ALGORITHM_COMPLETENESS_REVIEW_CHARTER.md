# PIX Algorithm Completeness Review Charter

**문서 상태:** Review charter (Ashlar → Provenance / Fathom → Vera)  
**기준일:** 2026-09-26 (Asia/Seoul)  
**Branch under review:** `feat/ocel-readers-v0.2.0` (package **0.5.0**)  
**관련 handoff:** Schumpeter `docs/audits/ASHLAR_DEVTEAM_BASELINE_2026-09-26.md` (동일 일자)

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
