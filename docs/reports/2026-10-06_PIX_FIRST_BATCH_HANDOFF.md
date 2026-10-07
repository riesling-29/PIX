# PIX 첫 개발 묶음 — 검토·게시 인계

공통 base: `a0688f34e557c885c145051485072fd0623f263f`.
2026-10-06 원격 재조회에서 개발 branch는 이 SHA, main은 `e7b67bcce6c67637bd76a0db20ce245fe9e4b0e6`였다. 아래는 완료한 로컬 작업이며 원격 반영 상태가 아니다.

## 게시할 구체 범위

대상 저장소 `riesling-29/PIX`, draft PR base는 모두 `feat/ocel-readers-v0.2.0`.

| Topic branch | 구현 commit | PR 제목·핵심 |
| --- | --- | --- |
| `docs/ocpm-plan-integration-20261006` | `ef10b22` + 이 인계 문서 후속 commit | `docs: integrate OCPM review sources and amended execution criteria` — 원문 4개·38개 요구·후속 정정 연결 |
| `ci/wheel-contract-20261006` | `ea82ae1` | `fix: honor platform dependencies in isolated wheel validation` — Windows tzdata marker/설치 계약, 26개 회귀 |
| `docs/ocpm-input-audit-20261006` | `3f2c139` | `docs: inventory OCPM inputs and audit existing P1 contracts` — 170개 정의 목록·20개 의미 감사·150개 미검토 명시 |
| `fix/python310-contracts-20261006` | `7df18a5` | `fix: preserve numeric and timestamp contracts on Python 3.10` — 6개 기존 실패와 table 동종 경로 수정, 신규 25개 반례 |

각 PR에 포함할 내용은 해당 commit의 문제·수정·실제 검증·잔여 제한이며, 다른 작업의 전체 완료를 주장하지 않는다. topic별 변경 경로는 서로 겹치지 않는다. 이 사실은 실제 통합 SHA의 NEXT-05 수락을 대신하지 않는다. 원문 PR #1/#2의 종료·병합·브랜치 삭제, main 변경, release/tag는 이 게시 범위에 포함하지 않는다.

## 확보한 근거

- DOC-00: 전문 보존과 Markdown 줄바꿈 정리만 적용; 원문과 정규화 후 비교. 38개 ID 중복/누락과 상대 링크 확인.
- NEXT-04: Linux 3.12의 dependency 회귀 26개 통과. 외부 wheel native/mining/visualization 세 검사 통과. Windows/macOS marker 분기 테스트는 실제 OS 실행과 구별.
- 최소 Python 검증: 첫 3.10 전체 실행에서 6개 실패 발견. 통계 overflow·소수초 parser·compact inference를 고치고 기존 기대값을 유지.
- 수정 제품 branch 전체: Linux Python 3.10.21과 3.12.14 각각 **10,549 pass / 40 skip / 1,169 subtests**. 변경 Python Ruff 통과.
- 수정 제품의 새 wheel: Python 3.10 source 밖 import·CLI·mining/visualization smoke 통과, 249개 source/wheel/install bytes 일치. 검사 도구는 `ea82ae1`판, 제품은 `7df18a5`판으로 분리 기록.
- NEXT-01: ETOT/OTG 비교·OCCN↔OCPN 제한적 양방향 변환·filter·enrichment 기존 경로를 확인. 참조 동일성·전체 의미 감사는 완료하지 않음.

관련 보고서 경로는 각각의 topic에 있다:

| Topic | 보고서 |
| --- | --- |
| DOC-00 | `docs/requirements/2026-10-06_PIX_INTEGRATED_EXECUTION_PLAN.md` |
| NEXT-04 | `docs/reports/2026-10-06_PIX_WHEEL_CONTRACT_VALIDATION.md` |
| NEXT-01 | `docs/reports/2026-10-06_PIX_OCPM_INPUT_AUDIT.md` |
| 3.10 수정 | `docs/reports/2026-10-06_PIX_PYTHON310_COMPATIBILITY.md`, `python310-2026-10-06/evidence.json` |

## 남은 범위

Chromium 다운로드 ZIP·lock 오류로 실제 browser 미실행. Windows/macOS 실제 실행, Python 3.13 독립 실행, 외부 corpus, P1 미검토 150개 정의의 의미 조사, OPERA arc annotation·flooding·표준 판본 상세 diff, NEXT-02/03/05와 참조 대체 검증이 남는다. 40 skip을 통과로 세지 않는다.

이번에 CI workflow·branch protection을 추가하지 않았다. 177개 사용자 선택·ILP 보류·PIX/Schumpeter 책임 경계는 유지한다. 새 알고리즘 공수·전체 대체율·실무 효용은 알 수 없음이다.

## 현재 상태와 재개

원격 push 시도는 자동 승인 검토가 명시적 외부 게시 승인 부족을 이유로 거절했다. 다른 경로로 재시도하지 않았으며 이후 원격 branch 조회에서도 기존 4개 branch만 확인했다. 로컬 구현·검증·commit은 완료했다. 다음 사용자 승인 대상은 위 4개 topic의 push와 draft PR 생성이다.

승인 후에는 원격 HEAD를 다시 읽고 base 이후 변경을 확인한 다음 topic별 게시·원격 SHA 확인·draft PR 생성을 한다. base가 그대로라면 전체 테스트를 단순 반복하지 않는다. 새 변경이나 반례가 있으면 영향받는 부분만 검토한다. 이 보고서는 위 commit·환경·요구에 유효하며 자기 자신을 포함한 diff hash는 쓰지 않는다.
