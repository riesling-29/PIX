# PIX 현재 변경 커밋 및 Vera 검토 인계

작성일: 2026-09-20. 대상 저장소: `riesling-29/PIX`.
대상 브랜치: `feat/ocel-readers-v0.2.0` (main 아님).
변경 이전 기준: `65cf9d557cfcbe1f8159b9a8600bb1aa60fe3fc9`.

## 검토 기준 고정

이 문서를 처음 추가한 커밋이 이번 검토 묶음이다. 자기 자신의 SHA를 문서에 넣으면 SHA가 바뀌므로, 정확한 식별자는 다음 명령 또는 GitHub의 파일 커밋 이력에서 확인한다.

```console
git log --diff-filter=A --format=%H -- docs/reports/2026-09-20_PIX_COMMIT_REVIEW_HANDOFF.md
```

검토자는 해당 SHA로 checkout한 소스와 아래 문서를 함께 읽는다. 브랜치 최신 상태는 이후 달라질 수 있다. GPT Mode에서 저장소 접근이 안 되면 해당 커밋의 소스 ZIP을 첨부한다. 로컬 경로나 SHA만 전달해서는 파일 내용이 전달되지 않는다.

## 요구와 책임 경계

PIX는 PM4Py/OCPA 계산 기능을 독립적인 native 구현으로 대체하려는 계산 엔진이다. **수집은 Agent, 계산은 PIX**이며 Schumpeter의 Hub 운영과 PIX의 계산을 구별한다. 기존 라이브러리 호출로 계산 구현을 대신하지 않는다. profile별 한계·정보 손실·중단 상태·원본 근거를 명시한다. ILP는 공동 학습·설계 전 착수 보류 상태를 유지한다.

## 읽을 문서 순서

1. [177개 공동 검토 체크리스트](../requirements/2026-09-18_PIX_REMAINING_177_JOINT_REVIEW_CHECKLIST.md): 사용자의 필요 여부와 조건 메모.
2. [잔여 세부 설계](../requirements/2026-09-18_PIX_RESIDUAL_DETAILED_DESIGN.md), [ID별 추적표](../requirements/2026-09-18_PIX_RESIDUAL_DESIGN_TRACEABILITY.md): R01–R14의 정의·범위·검증 조건.
3. [잔여 기반 구현 보고서](2026-09-18_PIX_RESIDUAL_CORE_IMPLEMENTATION.md): 이번에 실제로 추가한 profile, 대응 ID, 남은 범위.
4. [사용법](../user-guide/RESIDUAL_CORE_GUIDE.md)과 연결된 소스·테스트: 보고서와 실제 동작 대조.
5. [기존 기능 평가](2026-09-18_PIX_PM4PY_OCPA_COMPLETION_ASSESSMENT.md): 변경 이전 기준 SHA의 평가. **이번 구현 이후 완성률로 인용하면 안 된다.**

## 이번 커밋 범위

- XES/gzip 및 bytes 교환, DFG reader/writer, CSV/Parquet bundle writer, 손실 명시 OCEL 1 JSON writer.
- Process tree 및 PIX POWL text profile, 속성 sequence 추출, 합성 검산 로그 생성.
- inspect/dfg/ngrams/export-xes CLI와 명시 열 mapping.
- 객체별 CaseLog 투영과 원본·속성 이력·참여 관계 대응.
- 문맥 n-gram의 학습/적용 분리, count/binary/TF-IDF 및 실제 계산 샘플.
- 업무 달력·시간대·DST와 경로 위치별 성능 집계.
- POWL footprint, DFG causal 관계, 단일 trace 적합성 공통 API.
- 결과 schema 등록, 전용 테스트, Windows tzdata 의존성과 lock 갱신.
- 이전에 미커밋 상태였던 평가 자료·177개 협의/설계 문서·평가 도구를 함께 보존.

`.artifacts`, 가상환경, 다운로드 로그는 기존 ignore 정책을 유지한다. n-gram HTML/JSON/PNG와 JUnit은 로컬 산출물이며 커밋 대상이 아니다. 샘플은 커밋된 `examples/residual_ngram_review.py`로 재생성한다. PIX 밖에서 수행한 Foundation 보관 이동은 이 저장소의 커밋 범위가 아니다. `PIX-References`는 변경하지 않았다.

## 커밋 전 검증

2026-09-20 재실행 결과는 아래에 기록한다. 이전 9월 18일 검증과 구별한다.

- 전체 회귀: **10,503 passed, 39 skipped, 1,169 subtests passed**, 73.96초.
- 로컬 원시 결과: `.artifacts/2026-09-18-validation-residual-core/pytest-precommit-2026-09-20.xml`.
- skip: 선택 실행 브라우저 26개, 다운로드 XES corpus 11개, Python Playwright native dependency 문제에 따른 collection 1개, Windows symlink 권한 1개. 이 실행에서 해당 검증까지 통과했다고 주장하지 않는다.
- 변경·추가 Python 파일 37개: Ruff check 및 format check 통과.
- staged diff 공백 검사 통과. 추적표의 혼합 줄바꿈과 평가표의 마지막 빈 줄을 정규화했으며 사용자 판단·메모는 수정하지 않았다.
- 원격 fetch 후 커밋 전 HEAD와 해당 원격 브랜치의 차이는 0/0이었다. push 결과와 최종 SHA는 실행 응답 및 원격 Git 이력에서 확인한다.

검증 runtime은 허용된 Python 3.13.15이며 `.venv` 실행 정책을 수정하지 않았다. ABI가 맞는 PyArrow 25.0.1, tzdata 2026.4를 별도 로컬 dependency 경로로 제공했다. 일반 개발 환경에서는 프로젝트의 dev/parquet extra와 Windows 조건부 tzdata 의존성으로 구성한다.

```console
python -m pytest tests -q
python examples/residual_ngram_review.py --output <새 디렉터리>
```

## Vera에게 요청할 검토

요구사항과 구조의 일치, 계산 모집단·객체 공유·순서·시간 정의, 정보 손실 처리, 학습 자료 유입 방지, 탐색 한도의 의미를 검토한다. 보고서와 실제 함수·테스트를 대조하고, 기능 상태의 과장이나 누락을 찾는다. 문제에는 해당 파일·함수와 재현 입력 또는 반례를 붙인다. 문서 검토만으로 테스트를 실행했다고 표현하지 않는다.

177개는 잔여 검토 행이며 독립 알고리즘 수가 아니다. 이번 변경은 그 일부의 지원 profile을 보완한 것이다. 전체 대체 완료율·남은 공수·실무 성공률은 이 묶음만으로 **알 수 없음**이다.

지원 판단은 이 커밋과 명시된 입력 profile에 한정한다. 보존 데이터 손실, 잘못된 집계, case 경계를 넘는 n-gram, 검증 자료의 학습 유입, 탐색 중단의 부적합 확정이 재현되면 해당 판단을 철회한다. 코드·입력 계약·의존성이 바뀌면 관련 검증을 갱신한다. 이번 커밋을 전체 잔여 개발 완료 또는 main 병합으로 해석하지 않는다.
