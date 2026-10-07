# GitHub에서 시작하는 PIX 기준점 검증 인계

작성일: 2026-10-04. 대상: GPT Work / Cloud Codex / Dot / 로컬의 후속 검증 담당.

## 1. 반드시 고정할 기준

- 저장소: `riesling-29/PIX`
- 읽을 브랜치: **`feat/ocel-readers-v0.2.0`**. 기본 `main`은 이 작업의 기준이 아니다.
- **코드 기준 commit: `4e0b471f6eddb34d6b1818e7ef29398ae362d064`**.
- 기준 이전 commit: `2b515bcaa674f90cddf438fdfa4f6916e03e3d47`.
- 코드 기준 이후 이 인계서와 계획·링크를 추가하는 commit은 docs-only다. 이 문서 자신의 commit/hash를 문서에 재귀적으로 넣지 않는다. 소비자가 실제 checkout SHA를 기록한다.
- 제품 metadata: `pix 0.5.0`. 새 release나 PM4Py/OCPA 전체 대체 완료를 선언한 기준점이 아니다.

원격 최신 branch에 후속 코드 변경이 있다면 기준점 테스트와 최신 상태 테스트를 구분한다. 새 변경을 기준점으로 되돌리지 않는다. 읽기 전용 GitHub connector로 파일을 확인하는 것과 실제 Python/Node 테스트 실행은 다르다. shell/checkout이 없으면 정적 검토만 했다고 보고한다.

## 2. 읽을 순서

1. 이 문서와 README의 현재 지원 범위.
2. [후속 세부·병행 계획](../requirements/2026-10-04_PIX_PARALLEL_DEVELOPMENT_PLAN.md).
3. [도메인 사례](../user-guide/OCPM_DOMAIN_REVIEW_CASES.md): 특히 non-variable arc 해석과 projection 예제.
4. [진행·검증 기록](2026-09-28_OCPM_PATCH_PROGRESS.md): 마지막 2026-10-04 절이 이번 기준점의 실제 실행이다.
5. [소비 계약](../specifications/PIX_OCPM_CONSUMPTION_CONTRACT.md), [원래 패치 계획](../requirements/2026-09-28_OCPM_DETAILED_PATCH_PLAN.md).
6. 필요 범위의 기존 요구: `docs/requirements/2026-09-18_PIX_REMAINING_177_JOINT_REVIEW_CHECKLIST.md`, `2026-09-18_PIX_RESIDUAL_DETAILED_DESIGN.md`.

## 3. 기준점의 변경 범위

| 파일 | 변화 |
| --- | --- |
| `src/pix/viewer/visualization.py` | 입력별 `issues_json`; 완료된 ObjectReplay의 nonfit 안내; 선택적 `projection=`의 derived digest·source/spec 대응 검사와 panel provenance |
| `src/pix/viewer/assets/visualization.js` / CSS | 현재 panel에 맞는 해석 표시, 안전한 텍스트 렌더링, SVG footer |
| `tests/viewer/test_ocpm_domain_review.py` | 손계산·operator 구별·nonfit·실패 귀속·receipt 검사·codec·identity 테스트 7개 |
| `tests/viewer/test_visualization_ui.cjs` | panel 귀속·악성 문자열·SVG 보존 시나리오 |
| `tests/browser/test_visualization_browser.py` | 실제 브라우저 interpretation 시나리오와 artifact 출력 경로 선택 |
| `examples/ocpm_projection_review.py` | 합성 OCDFG와 projection Case DFG의 HTML/JSON |
| 기준점 문서 4개 | 세부 패치 계획, 소비 계약, 도메인 사례, 실행 기록 |

계산 알고리즘·canonical V1·projection v2 profile·result/model codec version은 이번 변경에서 바꾸지 않았다. visualization JSON에 선택적 provenance detail이 추가되므로 생성 bytes는 바뀐다. 계산 digest/computation ID 변경과 구분한다. `projection=`은 source/spec 재투영 비용이 있는 opt-in 경로이며 provenance 진실성 인증은 아니다.

## 4. 실제로 끝낸 로컬 검증과 한계

2026-10-04, Windows 11 build 26200, Python 3.13.15 AMD64, Node 24.18.0. pytest 9.1.1, Ruff 0.16.6, tzdata 2026.4, openpyxl 3.1.5, pyarrow 25.0.1.

| 검사 | 실제 결과 |
| --- | --- |
| 전체 source-tree pytest | 10,524 passed / 40 skipped / 1,169 subtests passed / 58.97초 |
| Node UI | 44 passed, 0 failed, 0 skipped |
| native visualization Chromium | 13 passed / 9.59초 |
| 변경 Python 4개 Ruff check/format | 통과 |
| 합성 projection 예제 | HTML/JSON 생성 성공 |
| diff 공백 검사 | 통과 |

40 skip은 opt-in browser 27, corpus 11, Python Playwright greenlet 로드 실패 1, Windows symlink 권한 1이다. browser 27 중 native visualization 13개만 따로 실행했다. 다른 환경에서 이 수가 달라져도 기대 수를 맞추기 위해 skip을 추가하지 않는다.

미실행: 깨끗한 lock 설치, wheel 격리 설치, Python 3.10, Linux/macOS, 나머지 browser suite, 외부 corpus, 규모별 비용. 위 시간은 이 한 번의 회귀 실행 시간이지 성능 benchmark가 아니다. 원격에서 같은 결과가 나온다고 보장하지 않는다.

로컬 상세 로그는 ignored `.artifacts/2026-10-04-ocpm-baseline/`에 있다. 원격에서 그 경로가 존재한다고 가정하지 않는다. 사용자 첨부 `docs/PIX_review_5ef88a2.zip`은 commit하지 않았으며 이번 테스트의 필수 입력이 아니다.

## 5. 원격 실행 절차 — 아래 명령은 후속 환경용 계획

기존 작업 폴더가 dirty라면 checkout하지 말고 별도 clone/worktree를 사용한다. 비밀정보를 로그에 출력하지 않는다. 개인 PC의 차단된 `.venv` 실행 정책은 바꾸지 않는다.

```bash
git clone --branch feat/ocel-readers-v0.2.0 <승인된-PIX-Git-URL> pix-review
cd pix-review
git status --short
git rev-parse HEAD
git log -5 --oneline
git show --stat 4e0b471f6eddb34d6b1818e7ef29398ae362d064
```

새 disposable clone에서 정확한 코드 기준만 시험하려면 `git switch --detach 4e0b471f6eddb34d6b1818e7ef29398ae362d064`를 사용한다. 기준 후의 인계 문서는 먼저 읽어둔다. 결과를 저장할 필요가 있으면 별도 검증 브랜치를 만들되 이번 인계만으로 commit/push/merge하지 않는다.

### 5.1 설치와 환경 기록

uv가 사용 가능한 새 환경의 권장 재현 경로:

```bash
uv --version
uv sync --locked --extra dev --extra imports
uv run --no-sync python --version
uv pip freeze
node --version
```

uv가 없고 설치도 허용되지 않으면 승인된 새 Python 환경에서 `python -m pip install -e '.[dev,imports]'`로 실행할 수 있다. 이 경우 lock 재현이 아닌 dependency resolution 실행임을 기록하고 `python -m pip freeze`를 남긴다. 아래 `uv run --no-sync python`을 그 환경의 Python으로 치환한다. 두 설치 방식을 섞어 lock 검증이라고 주장하지 않는다. 이미 사용하는 환경·보안 설정을 바꾸지 않는다.

### 5.2 집중·전체·JS·예제

```bash
uv run --no-sync python -m pytest tests/viewer/test_ocpm_domain_review.py tests/viewer/test_visualization.py tests/object_centric/test_conformance.py tests/object_centric/test_case_projection.py tests/object_centric/test_review_identity.py tests/test_review_boundaries.py -q -rs
uv run --no-sync python -m pytest tests -q -rs
node --test tests/viewer/test_visualization_ui.cjs
uv run --no-sync python examples/ocpm_projection_review.py --output .artifacts/work-review/projection-example
uv run --no-sync python -m ruff check src/pix/viewer/visualization.py tests/browser/test_visualization_browser.py tests/viewer/test_ocpm_domain_review.py examples/ocpm_projection_review.py
uv run --no-sync python -m ruff format --check src/pix/viewer/visualization.py tests/browser/test_visualization_browser.py tests/viewer/test_ocpm_domain_review.py examples/ocpm_projection_review.py
git diff --check
```

실행마다 새 artifact 디렉토리를 사용한다. 예제 출력이 이미 있으면 다른 새 경로를 사용한다. 예제 HTML/JSON 생성과 실제 브라우저 렌더링을 구분한다. 전체 suite는 opt-in browser/corpus를 자동 실행하지 않는다.

### 5.3 실제 브라우저 — 설치와 권한이 허용될 때

아래는 POSIX shell 예시이며 Windows는 환경변수 문법만 바꾼다. 시스템 의존성 설치가 필요하지만 허용되지 않으면 차단으로 기록한다.

```bash
uv sync --locked --extra dev --extra imports --extra browser
uv run --no-sync python -m playwright install chromium
export PIX_PLAYWRIGHT_MODULE="$(uv run --no-sync python -c 'import pathlib, playwright; print(pathlib.Path(playwright.__file__).parent / "driver" / "package")')"
export PIX_RUN_BROWSER=1
export PIX_BROWSER_ARTIFACTS="$PWD/.artifacts/work-review/native-browser"
uv run --no-sync python -m pytest tests/browser/test_visualization_browser.py -q -rs
unset PIX_RUN_BROWSER
```

native visualization runner는 Node와 Playwright Node package·Chromium을 사용한다. 다른 browser suite는 각 파일의 실행 전제와 artifact 경로를 먼저 확인한다. 기존 역사 artifact를 덮어쓰지 않는다. 외부 corpus는 원격에 자동 배포되지 않는다. 합성 테스트만 실행하고 corpus를 실행한 것으로 적지 않는다.

### 5.4 wheel 독립성 — 후속 필수 검증

1. 빌드 도구가 허용된 환경에서 `uv build --wheel` 또는 `python -m build --wheel`로 이번 source의 wheel을 만든다. 실행한 명령과 build dependency를 기록한다.
2. 저장소 밖의 새 가상환경에 **생성한 wheel의 절대경로**를 설치한다. PyPI의 동명 `pix`를 대신 설치하지 않는다.
3. 저장소 밖에서 PYTHONPATH를 제거하고 `python -I -c "import pix; print(pix.__file__)"` 및 설치된 `pix --help`를 실행한다.
4. 합성 예제 파일만 외부 작업 폴더에 복사하여 설치된 Python으로 실행한다. 생성 HTML의 asset 포함과 JSON 읽기를 확인한다. source tree를 sys.path에 추가하지 않는다.
5. wheel 경로/hash, 설치 내역, import 위치, CLI 종료 코드, 예제 결과를 보고한다. pytest source 실행만으로 이 항목을 통과 처리하지 않는다.

## 6. 도메인 수락 기준

- A→B count: 원본 event pair 2 / distinct object 2 / object-pair occurrence 3. 추가 qualifier가 곱셈을 만들지 않는다.
- non-variable T형 binding 반례: A(x,y)는 해당 모델에 부적합. A(x), A(y)는 적합할 수 있다. 이 사례로 variable arc 또는 다른 객체형을 일괄 거부하지 않는다.
- flattened 적합성이 joint 원본 판정을 덮지 않는다. token replay와 최적 alignment의 척도를 구분한다.
- projection receipt가 없으면 원본 lineage를 복원했다고 하지 않는다. 다른 digest·변조 대응은 거부하며 정상 단일 입력과 문서 합성은 보존한다.
- 화면의 계산 미완료·부적합·관측성 미입증·evidence 생략은 각각 다르다.
- 입력별 진단은 다른 panel에 새지 않아야 하며, 임의 문자열은 실행되는 HTML이 되면 안 된다.
- 독립 oracle의 기대값에 production 알고리즘을 재사용하지 않는다. codec roundtrip 테스트는 직렬화 검증이며 독립 계산 oracle이라고 부르지 않는다.

## 7. GPT Work에 붙여넣을 요청

```text
riesling-29/PIX의 feat/ocel-readers-v0.2.0 브랜치를 읽어줘.
main을 기준으로 검토하지 마.
먼저 docs/reports/2026-10-04_PIX_GITHUB_VALIDATION_HANDOFF.md와
docs/requirements/2026-10-04_PIX_PARALLEL_DEVELOPMENT_PLAN.md를 읽어줘.
코드 기준은 4e0b471f6eddb34d6b1818e7ef29398ae362d064야.
현재 checkout SHA와 기준 이후 변경을 구분해서 기록해줘.

우선 구현 확장 없이 기준점 교차검증을 진행해줘.
shell/checkout이 있으면 문서의 집중·전체·JS 테스트와 가능한 browser,
wheel 격리 smoke를 실행하고 실제 결과를 보고해줘.
GitHub 파일 읽기만 가능하면 정적 검토라고 명시하고 실행했다고 쓰지 마.
로컬 .artifacts, 개인 PC, 첨부 ZIP이 있다고 가정하지 마.
실패 시 최초 명령·환경·반례·기대 근거를 보존해줘.
기대값을 낮추거나 skip/xfail을 추가하여 성공으로 만들지 마.

코드나 기존 테스트 의미를 수정하기 전에 결함을 보고해줘.
결과 문서를 만들 수 있다면 docs/reports/에 실제 날짜와 검증 범위를 기록해줘.
commit/push/merge/main 변경은 이번 요청에 포함하지 않아.
최종 답은 확인한 것 / 실행 결과 / 재현 결함 / 미실행·차단 / 다음 작업으로 구분해줘.
```

## 8. 보고서 양식과 유효성

| 항목 | 기입 내용 |
| --- | --- |
| 기준 | base SHA / 실제 HEAD / branch / dirty 여부 |
| 환경 | OS / Python / Node / 설치 명령 / lock 사용 여부 / 실제 dependency |
| 각 검사 | 명령 / exit code / passed / failed / skip 사유 / 시간 / 첫 실패·재시도 |
| 독립성 | source vs wheel / import 경로 / 로컬 파일 의존 / oracle 모델군 |
| 발견 | 파일·함수 / 반례 / 기대 근거 / 수정 제안 또는 무변경 이유 |
| 남은 범위 | OS·Python·browser·corpus·extras·성능·통합의 미실행 |

이 문서는 기준 코드와 명시된 요구에 유효하다. 후속 코드·환경·표준 변경이나 독립 반례가 나타나면 영향받은 결과를 재검증한다. 플랫폼별 실제 실행 가능 여부와 미측정 비용은 알 수 없음이다. 보고서의 과거 통과 수는 후속 환경의 통과 증거가 아니다.
