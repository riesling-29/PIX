# PIX 기준점 이후 세부 개발·병행 작업 계획

작성일: 2026-10-04. 상태: **계획 / 아래 신규 작업 브랜치와 PR은 아직 생성하지 않음**.

코드 기준: `4e0b471f6eddb34d6b1818e7ef29398ae362d064`.
현재 통합 브랜치: `feat/ocel-readers-v0.2.0`.
이 문서는 [9월 패치 계획](2026-09-28_OCPM_DETAILED_PATCH_PLAN.md)의 후속 실행 명세다. 원래 요구와 177개 사용자 선택을 대체하지 않는다.

## 1. 확정된 기준과 이번에 하지 않은 일

- 기준 commit은 viewer 입력별 진단, 선택적 projection receipt 연결, panel별 설명·SVG 보존, 완료된 ObjectReplay 부적합 표시, 테스트·예제를 포함한다.
- non-variable arc에 연결된 객체형은 binding에서 정확히 하나를 선택한다. variable arc 전체나 활동 동시 실행으로 확대하지 않는다. variable min/max는 PIX 확장 profile이다.
- 수집은 Agent, 계산은 PIX. PM4Py/OCPA runtime backend, Hub, Agent harness, Schumpeter 저장소 변경은 범위 밖이다.
- Canonical V1, projection v2, 기존 result/model codec, operator identity와 계산 수식을 표시 편의 때문에 바꾸지 않는다.
- ILP discovery는 공동 학습·설계 전 착수 보류한다. 미확인은 미구현이라는 뜻이 아니다.
- `main`은 아직 현재 개발 기준이 아니다. 2026-10-04 fetch 후 확인한 `main`은 `e7b67bc`, 개발 브랜치의 작업 전 HEAD는 `2b515bc`였다. 실제 작업 시작 때 다시 fetch·확인한다.
- 이번 단계에서 main merge, branch protection 설정, CI workflow 생성, 개발팀 메시지 전송은 하지 않았다.

## 2. 작업 순서와 병렬 경계

먼저 [원격 검증 인계서](../reports/2026-10-04_PIX_GITHUB_VALIDATION_HANDOFF.md)에 따라 기준점 검증을 한다. 환경 구축 실패와 계산 실패를 분리한다. 재현된 결함은 영향받는 작업보다 우선한다.

| 작업 ID | 브랜치 제안 | 담당 모듈·산출물 | 선행 / 병행 조건 |
| --- | --- | --- | --- |
| PIX-NEXT-00 | `test/ocpm-baseline-validation` | 검증 결과 보고서, 재현 fixture | 첫 원격 실행. 원칙적으로 production 수정 없음 |
| PIX-NEXT-01 | `docs/ocpm-p1-gap-audit` | 전 연산 입력 사용표, P1 판정표 | 기준점에서 시작 가능; 다른 작업 코드는 읽기만 |
| PIX-NEXT-02 | `feat/ocpm-consumption-ui` | viewer adapter/JS/CSS/export 및 전용 테스트 | 기준점과 관련 도메인 사례 확정 후 |
| PIX-NEXT-03 | `test/ocpm-limits-quality` | variant/approximation/n-gram 전용 검증과 실험 | 01의 해당 정의 확인 후; UI와 병행 가능 |
| PIX-NEXT-04 | `ci/package-validation` | 패키징·환경 matrix·CI 제안/구현 | 기준점에서 시작 가능; production API 수정 금지 |
| PIX-NEXT-05 | 별도 통합 검증 PR | 최종 수락·문서 연결 | 실제 병합된 01~04 범위를 대상으로 수행 |

실행 환경은 업무 담당과 별개다. Work/Cloud Codex/Dot/Local Codex의 실제 파일·실행·인증·push 가능 여부를 확인한 뒤 배정한다. 이 문서가 각 제품의 기능 지원을 보증하지 않는다. 한 작업은 환경을 바꿔 인계할 수 있지만 동시에 두 writer가 같은 브랜치에 쓰지 않는다.

## 3. 작업 카드

### PIX-NEXT-00 — GitHub 기준점 독립 실행

목표: 로컬 artifact에 의존하지 않고 source 테스트·예제·패키지 진입점이 작동하는지 확인한다.

읽을 것: 인계서, pyproject.toml, uv.lock, 도메인 사례와 baseline 테스트 7개.
수정 허용 범위: 별도 실행 보고서, 필요할 때 최소 재현 테스트. 기존 테스트 expectation/skip 변경으로 실패를 감추지 않는다.

수락 조건:

- [ ] 실제 checkout SHA, dirty 상태, OS/Python/Node/dependency를 기록.
- [ ] 집중 테스트, 전체 테스트, Node UI, 실행 가능한 browser를 별도 결과로 기록.
- [ ] wheel 검증 시 source tree 밖에서 import 경로·CLI·viewer asset 사용을 확인.
- [ ] 첫 실패·재시도·skip·환경 차이를 보존하고 로컬 수치와 단순 일치시키지 않음.
- [ ] 결함은 함수·fixture·기대 근거·재현 명령과 함께 후속 수정 대상으로 제시.

### PIX-NEXT-01 — 계산 입력 사용과 조건부 P1 공백

owner: `compute/`와 `object_centric/`는 조사만 한다. 결과는 `docs/specifications/PIX_OCPM_CONSUMPTION_CONTRACT.md` 및 작업 전용 판정표에 기록한다. 다른 lane은 이 문서를 동시에 편집하지 않는다.

입력 사용표의 각 행에는 공개 함수, spec/profile, qualifier 선택, 객체 이력의 as-of 사용 여부, 보존만 하는 정보, observation cutoff, 결과 필드, 반례·테스트를 연결한다. 미사용 정보가 실제 사용된 것처럼 표시되는지도 조사한다.

P1 개별 조사:

| 대상 | 확인할 경계 | 최소 수락 근거 |
| --- | --- | --- |
| Object context | binding-prefix, 모집단, 종료·미확정 | 작은 prefix 손계산과 공개 결과 필드 대조 |
| OPERA/성능 annotation | 계산값·요약 통계·관측 범위 | 반복 pair/결측/0분모 반례 |
| Replay silent/flooding | silent closure 한도, flooding 정의 | bounded 모델의 독립 token 추적; 참조 동일성은 별도 |
| Filter | time/lifecycle/performance 조건 | 경계 시각·빈 결과·누락 관측 fixture |
| ETOT/OTG 비교 | 현재 graph comparison이 보장하는 대상 | 두 작은 그래프와 기대 차이 |
| OCCN↔OCPN | 양방향 지원, 손실, 표현 불가 | 손으로 정의한 모델과 방향별 손실 설명 |
| Lifecycle enrichment | first/last, singleton, 기존 qualifier 충돌 | 기존 수작업 fixture 재사용·공백만 추가 |
| OCEL 2.1 | 실제 공개 판본 vs 구현 pre4 | 확인 날짜·공식 문서·필드별 diff; 판본 미확인은 미확인 |

각 항목을 `기존 충족 / 문서·정책 노출 필요 / 재현 결함 / 신규 알고리즘 필요 / 검증 차단`으로 작업 보고한다. 새 runtime enum은 만들지 않는다. 신규 알고리즘은 이 조사 PR에서 착수하지 않고 정의·인수 반례·호환 영향이 있는 별도 패치를 제안한다.

### PIX-NEXT-02 — 소비 화면·내보내기 완성

owner: `src/pix/viewer/`의 관련 adapter, `visualization.py`, `assets/visualization.js`, CSS, export 경로와 `tests/viewer/`, 관련 browser 테스트. 공통 계산 계약은 수정하지 않는다.

순서:

1. OCDFG event pair/object/occurrence 선택과 label·legend를 대조한다. qualifier 수를 occurrence에 더하지 않는다.
2. joint alignment/object replay/flattened의 operator·정의·모집단을 구별한다. 숫자의 같고 다름을 정답 판별기로 쓰지 않는다.
3. OCPN 관측 witness와 joint soundness 미입증을 구별한다. raw/imported 모델에 discovery 배지를 붙이지 않는다.
4. computed/partial/unavailable/invalid_input과 payload 종료 상태를 교차 확인한다. evidence 생략만으로 계산 미완료라고 하지 않는다.
5. projection receipt 없음·불일치·다중 입력·nested composition·큰 shared-event 목록을 확인한다. 요약 표시가 lineage 삭제로 이어지면 안 된다.
6. 작은 화면·긴 한글/ID·키보드 focus·색 이외 설명·Chevron 양방향을 검증한다. 슬롯은 경과시간이 아니다.
7. HTML/JSON/SVG 및 실제 지원하는 기타 export별 의미 보존/생략을 기록한다. 렌더링 실패와 계산 실패를 구분한다.

수락: 손계산 fixture → 결과 → viewer codec → 실제 브라우저 → export의 동일 의미를 확인한다. 실제 화면은 minero 선생님이 도메인·가독성을 검토할 샘플로 제공한다. 기존 snapshot을 덮어쓰지 않는다. 대규모 receipt 재투영의 시간·메모리는 측정 전 알 수 없음이다.

### PIX-NEXT-03 — 한도·근사 품질·sequence

owner: 새 전용 테스트/실험 파일과 보고서. `compute/variants.py`, `compute/object_conformance.py`, `case_centric/context_ngrams.py`, `conformance_approximation.py`는 기본 읽기 대상이다. 재현 결함 수정은 파일 ownership을 먼저 공유한다.

- Exact variant: 성공·정상 empty·label budget·공유 budget·순서 미확정 사례를 분리한다.
- Approximation: 비용 경계의 독립 최적값 포함, witness 실행 가능성을 검증한다. 통계적 신뢰구간으로 재해석하지 않는다.
- 실험 전 fixture, seed, subset 크기, 탐색 budget을 고정한다. 각 실행의 구간 폭·탐색 수·미해결 수·측정 시간을 기록한다. 중단도 결과다.
- n-gram: A→B→A→B의 unigram A=2/B=2, bigram AB=2/BA=1 같은 명시적 token 예제를 먼저 제시한다. 실제 tokenizer/profile과 연결하고 tie 선형화 변경 효과를 보여준다. 일반 sequential pattern mining 지원으로 확대하지 않는다.
- 기대값 계산에 검증 대상 production firing/alignment를 재사용하지 않는다. oracle의 모델군과 탐색 완료 여부를 명시한다.

수락: 독립 기대값·metamorphic 조건과 반증 가능한 품질 자료가 있으며, 미측정 성능·전체 대체율을 수치로 만들지 않는다. 의미 변경이 필요하면 해당 항목만 사용자 판단을 요청하고 독립 작업은 계속한다.

### PIX-NEXT-04 — 깨끗한 패키지와 실행 환경

owner: 패키징 검증 스크립트, 새로운 `.github/workflows/`가 필요하면 해당 workflow, 작업 보고서. `pyproject.toml`/`uv.lock` 변경은 설치 결함을 재현한 경우에만 최소 수정하며 이유·lock diff를 연결한다.

- 지원 최소 Python 3.10과 개발 검증 Python 3.13을 우선 구분한다. Windows/Linux/macOS에서 실행·미실행을 각각 표시한다.
- editable source 테스트와 wheel을 설치한 저장소 밖 smoke를 분리한다. 우연한 PYTHONPATH·로컬 `.artifacts`에 의존하면 결함으로 기록한다.
- core, imports extras, browser, 외부 corpus, JS를 별도 job/기록으로 나눈다. optional 미설치 진단도 검증한다.
- CI를 추가한다면 처음에는 실행 범위와 비용을 좁게 정한다. private corpus 업로드, 보안 설정 변경, 로컬 차단 Python 우회는 하지 않는다.
- 기존 `.github/workflows`는 기준점에서 없다. branch protection은 자동으로 생기지 않으며 별도 저장소 설정 작업이다. 동작을 검증한 job만 필수 check 후보로 제시한다.

수락: wheel import·CLI·viewer assets의 실제 증거, dependency 기록, 환경 matrix가 있다. 미실행 OS를 지원 검증 완료로 표시하지 않는다.

### PIX-NEXT-05 — 통합 수락

실제 병합된 SHA를 고정하고 집중·통합·전체 검증을 수행한다. 변경된 공통 계약과 golden/projection identity를 다시 확인한다. 01의 발견을 전부 신규 구현 완료로 올리지 않는다. 사용자에게 작은 도메인 사례와 화면 샘플을 제시하고, 별도 판단은 미정 의미·호환 변경에 한정한다.

## 4. 브랜치·PR·인계 규칙

1. 최신 원격을 읽고 기준 branch/SHA를 기록한다. 현재는 `feat/ocel-readers-v0.2.0`이 통합 대상이다. 최신 통합 HEAD가 기준점의 후손인지 확인하고 새 변경을 읽는다. `main`에서 무심코 시작하지 않는다.
2. 한 작업 = 한 짧은 topic branch = 한 writer. 환경별 영구 branch는 만들지 않는다. 같은 PC 병행은 별도 worktree/checkout을 사용한다.
3. 업무 시작 기록에 작업 ID, branch, base SHA, 담당 파일, 제외 범위, 완료 조건, 상태를 남긴다. 팀 메시지 발송은 사용자 승인 범위에서만 한다.
4. 공통 파일을 두 작업이 수정해야 하면 owner를 하나로 정하거나 선행 PR 후 다음 작업을 시작한다. 충돌 없는 merge도 의미적 호환성의 증거는 아니다.
5. PR에는 문제·정의·반례·실제 검사·skip·잔여 한계를 적는다. 코드 생성 agent 자신의 통과 선언만으로 병합하지 않는다.
6. PR을 하나씩 검토·병합하고 다음 PR은 갱신된 통합 기준으로 회귀한다. 공동 사용 브랜치 force push나 기존 작업 rollback은 하지 않는다.
7. 현재 개발분을 검증해 main에 반영하는 작업은 별도다. 그때 main을 기준으로 바꾼다. release가 여러 개가 아니라면 영구 develop/release 계층은 당장 추가하지 않는다.

환경을 옮길 때는 마지막 pushed SHA, 미완료 항목, 실행/미실행 결과, 다음 담당을 인계한다. PC에만 있는 미커밋 diff는 원격 인계가 아니다. 코드·문서 push는 각 작업의 사용자 승인 범위를 따른다. 이 계획만으로 모든 agent에 임의 push/merge 권한을 부여하지 않는다.

## 5. 상태 보고 양식과 재검토 조건

```text
작업 ID / 담당 환경 / branch / base SHA / 현재 SHA:
수정 파일과 실제 의미 변경:
완료한 수락 조건:
명령 / 환경 / 결과 / 첫 실패 / skip:
사용자 판단이 필요한 정확한 반례:
남은 것 / 다른 작업과 겹치는 파일:
다음 인계:
```

현재 표의 항목은 구현 약속 범위와 검증 계획이며 진행률·알고리즘 수·공수 추정치가 아니다. 시간·비용·실무 성공률은 알 수 없음이다. 기준 코드·요구·표준·profile이 바뀌거나 독립 반례가 나오면 해당 카드만 재검토한다. 기존 구현이 충분하면 제품 코드 무변경으로 해당 항목을 마칠 수 있다.
