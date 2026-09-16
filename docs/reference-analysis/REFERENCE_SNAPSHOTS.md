# 참조 스냅샷 / Reference snapshots

기록일: **2026-09-12**. 이 파일은 기존 분석 문서에 있던 기준선과 이번 공식 조회를 구분한다.
이전 레지스트리는 TBD 상태였으나 개별 분석 문서에는 SHA가 기록되어 있었다.
이번 기록을 과거에 수행한 설치·시험의 증거로 소급하지 않는다.

| 항목 | PM4Py | OCPA |
|---|---|---|
| 공식 저장소 | [process-intelligence-solutions/pm4py](https://github.com/process-intelligence-solutions/pm4py) | [ocpm/ocpa](https://github.com/ocpm/ocpa) |
| 로컬 경로 | `D:\ChantaResearchGroup\PIX-References\pm4py-upstream` | `D:\ChantaResearchGroup\PIX-References\ocpa-upstream` |
| 로컬 브랜치 | `release` | `main` |
| 로컬 SHA | `3329bbcbadce8764f7df660fd88636c30793fbd0` | `de056e0203a3fa4a9bbc19a95e001eada323074a` |
| 로컬 소스 버전 | `2.7.23.3` | `1.3.3` |
| 기존 전체 구조 분석일 | 2026-07-19 | 2026-07-23 |
| 2026-09-12 로컬 확인 | working tree clean, SHA 유지 | working tree clean, SHA 유지 |
| 이번 공식 브랜치 조회 SHA | `24a3bf610aea6ecc4938b1864b3ad71fcfb82084` (`release`) | `de056e0203a3fa4a9bbc19a95e001eada323074a` (`main`) |
| 이번 PyPI 최신 조회 | `2.7.23.8` / 2026-09-01 | `1.3.4` / 2025-09-19 |
| 9월 9일 기록과 비교 | 동일한 공식 SHA·배포 버전 재확인 | 동일한 공식 SHA·배포 버전 재확인 |
| 이번 upstream 설치 명령 | 수행하지 않음 | 수행하지 않음 |
| 이번 upstream 전체 시험 명령·결과 | 수행하지 않음 | 수행하지 않음 |
| 이번 runtime 검증 Python 버전 | 해당 없음: 정적 조사 | 해당 없음: 정적 조사 |

공식 출처:

- [PM4Py 고정 소스](https://github.com/process-intelligence-solutions/pm4py/tree/24a3bf610aea6ecc4938b1864b3ad71fcfb82084),
  [현재 release 조회 API](https://api.github.com/repos/process-intelligence-solutions/pm4py/commits/release),
  [배포 metadata](https://pypi.org/pypi/pm4py/2.7.23.8/json).
- [OCPA 고정 소스](https://github.com/ocpm/ocpa/tree/de056e0203a3fa4a9bbc19a95e001eada323074a),
  [현재 main 조회 API](https://api.github.com/repos/ocpm/ocpa/commits/main),
  [배포 metadata](https://pypi.org/pypi/ocpa/1.3.4/json).

브랜치 조회 API와 latest 배포 정보는 변할 수 있다. 개별 소스 판단에는 위 고정 SHA의 링크를 사용한다.
로컬 reference checkout과 Git ref는 이번 조사에서 갱신하지 않았다.

PM4Py 현재 소스·배포 metadata의 Python 요구는 `>=3.11`이다. README의 이전 Python 안내와
구분한다. 이것은 실제 설치 성공을 확인했다는 뜻이 아니다. OCPA의 main 소스 버전 1.3.3과
배포 버전 1.3.4도 구분한다. 9월 9일 문서에 기록된 일부 I/O 파일의 wheel/source 동일성은
그 파일들에 한정하며 전체 계산 코드의 동일성을 뜻하지 않는다.

이번 OCPA 알고리즘 파일의 wheel/source 추가 대조는 완료하지 못했다. 메모리 내 .NET wheel
다운로드·Git blob 비교 명령은 자동 승인 검토에서 `blocked by policy`로 거부됐으며 재시도하지 않았다.
해당 일치 여부·개수는 **알 수 없음**이다. PyPI에 기재된 wheel SHA256
`52e8208d5ef8633060b905441498aa8b53e0322bf7a310c5a5deb49500da2934`는 배포 metadata 값이며,
이번에 독립적으로 다운로드해 재계산한 값이 아니다.

결과: [2026-09-12 구조 재조사](comparison/2_PM4PY_OCPA_STRUCTURE_REFRESH_2026-09-12.md).
과거의 제한된 실행 관찰은 각 원문 문서가 소유한다. 이번 재조사의 근거는 문서·고정 소스·배포
metadata이며, 정확성·성능·전체 표준 호환성을 입증하는 새 runtime 시험 결과는 없다.

These entries separate the historical local checkouts from the upstream versions observed on
2026-09-12. No upstream package installation or full runtime suite was performed for this refresh.
The OCPA wheel/source algorithm comparison was not completed; earlier I/O-only evidence must not
be generalized to the full distribution. Recheck affected claims when commits, distributions,
backends, or relevant standards change.

## 2026-09-14 — SCOPE-01 공식 wheel 원천 대조

위 9월 12일의 미완료 기록과 구분하는 새 조사다. 공식 PyPI 조회 시각은
**2026-09-14T21:34:37.4954807+09:00**이며 PM4Py 2.7.23.8·OCPA 1.3.4를 다시 확인했다.
두 wheel을 다운로드하고 metadata SHA와 실제 SHA를 대조한 뒤 격리된 자료 디렉터리에
추출했다. 참조 라이브러리는 설치·import·실행하지 않았다. 이전 reference checkout도 수정하지 않았다.

| 항목 | PM4Py | OCPA |
|---|---|---|
| 고정 배포 metadata | [2.7.23.8](https://pypi.org/pypi/pm4py/2.7.23.8/json) | [1.3.4](https://pypi.org/pypi/ocpa/1.3.4/json) |
| 실제 wheel bytes | 2,666,577 | 213,756 |
| Python 소스 파일 | 1,658 | 203 |
| 이전 소스와 byte 동일 | 1,584 | 198 |
| AST 변경 / AST 동일·byte 상이 / 추가 | 73 / 0 / 1 | 3 / 1 / 1 |
| AST parse 오류 | 0 | 0 |

재계산하여 일치한 SHA-256:

- PM4Py: `e97f7845bc440859fe46e88824bb773162d8799f1278b34907d0eb4c7d4be502`.
- OCPA: `52e8208d5ef8633060b905441498aa8b53e0322bf7a310c5a5deb49500da2934`.

로컬 원천 자료: `.artifacts/scope-01-2026-09-14/`의 `upstream.json`, `downloads.json`,
`source-inventory.json`, `baseline-diff.json` 및 각 `*-wheel/` 디렉터리.
보관용 [원천 목록](../requirements/scope-01/reference_catalog.json)과
[파일별 차이](../requirements/scope-01/baseline_diff.json)는 소스 코드 대신 경로·hash·식별자를 기록한다.
공식 wheel URL은 [대체 레지스트리](../requirements/scope-01/replacement_registry.json)에 고정했다.

AST 비교에는 상수와 docstring도 포함되며 runtime 동치를 입증하지 않는다.
이번에 새로 포착한 기능의 도입 시점을 추정하지 않는다. 실제 추가 파일은 PM4Py
`algo/conformance/alignments/petri_net/variants/dijkstra_semantics.py`와 OCPA
`algo/util/filtering/log/index_based_filtering.py`다.

결과: [SCOPE-01 대체표](../requirements/2026-09-14_PIX_SCOPE_01_REPLACEMENT_MATRIX.md).
이번 산출물은 334개 검토 항목의 입력·출력·현재 PIX 상태·의미 차이·근거·개발 작업 연결이다.
공개 진입점 및 추출 selector의 미연결 항목은 0개이나, 계산 정확성·runtime 호환·대체 승인과는 구분한다.
