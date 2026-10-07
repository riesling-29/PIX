# 라벨별 대표 Trace 비교 — 구현 및 검증

검증일: 2026-10-07. 기준 커밋: `2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3`.
작업 대상은 `work` 브랜치다.

## 구현 범위

기존의 개별 panel/tab 탐색에 더해, 정상/비정상 또는 여러 그룹의 대표 case
sequence를 **한 panel**에서 기준 대표와 비교한다.

- `compare_trace_groups`: case 속성 라벨 또는 명시적 `TraceGroup` membership.
- 기본 대표는 최빈 활동 sequence의 실제 case이며, 수동 case 지정도 지원한다.
- 후보 기본 3개, 그룹 전체 분모의 빈도, 후보 coverage와 unassigned case 보존.
- 각 후보 쌍의 양방향 weighted edit alignment를 Python에서 사전 계산한다.
- 브라우저에서 기준·대표 후보·표시 그룹·차이 열 필터를 변경한다.
- 추가·누락·치환·일치를 구분하고 원 case/event ID를 검사할 수 있다.
- 현재 선택 화면과 설명을 SVG로 저장한다. 원 계산 JSON은 변경하지 않는다.
- 공개 계산 결과 codec, 시각화 codec, lazy API와 명시적 모듈 registry에 등록했다.

사용법: [TRACE_GROUP_COMPARISON_GUIDE.md](../user-guide/TRACE_GROUP_COMPARISON_GUIDE.md).
실행 예제: `examples/trace_group_comparison_demo.py`.

## 검증 결과

| 검사 | 결과 |
| --- | --- |
| Linux Python 3.10.21 전체 pytest | 10,597 passed, 41 skipped, 1,169 subtests passed |
| Linux Python 3.12.14 전체 pytest | 10,597 passed, 41 skipped, 1,169 subtests passed |
| Node viewer UI suite | 48 passed |
| 실제 Chromium 153.0.8010.0 비교 화면 | 1 passed; 아래 5개 흐름 확인 |
| 수정 Python 파일 Ruff lint / format | 통과 |
| `git diff --check` | 통과 |
| 별도 Python 3.10 환경의 wheel 설치 검사 | 계산, JSON roundtrip, 단일 panel, 독립 HTML 생성 통과 |

실제 브라우저에서는 세 라벨 그룹의 단일 캔버스, 대표·기준·표시 그룹·차이 필터,
선택한 화면의 SVG 다운로드, 390px viewport의 페이지 가로 넘침 없음,
HTTP 요청 및 console/page error 없음을 확인했다. 한글 폰트를 설치한 환경에서
1440px 및 390px 화면을 직접 확인했다. 작은 화면에서는 기존 Readable/확대·이동
조작을 사용할 수 있다. SVG의 설명은 줄바꿈 후 텍스트를 복원해 검사한다.

새 계산 테스트 21개는 그룹 membership과 빈도, 수동 대표, 반복 활동과 빈 trace,
빈 그룹, 라벨 충돌/누락, 계산 한도, 원 event ID, JSON 보존과 잘못된 정렬 증거를
검사한다. 짧은 sequence에 대한 독립 재귀 편집 비용 oracle로 단위 비용,
비대칭 비용/치환 비활성, 0 비용을 대조했다. 공통 native codec 검사에도
새 모듈의 실제 계산 결과를 추가했다.

전체 pytest의 opt-in 브라우저/XES corpus 및 Windows 전용 검사는 기본 설정에서
skip됐다. 위 비교 화면의 브라우저 검사는 별도로 활성화해 실행했다. Windows,
macOS와 다른 브라우저 엔진은 이번 작업에서 실행하지 않았다.

검사한 wheel SHA-256:
`577b5a315ee30d3fbb483097cacf3200d804136598eaa4baf4ffd290ddc4fcb9`.

## 재현

```bash
python -m pytest -q
node --test tests/viewer/test_visualization_ui.cjs
python examples/trace_group_comparison_demo.py --output .artifacts/trace-group-comparison
```

실제 브라우저 실행 설정은 `tests/browser/README.md`를 참조한다.

## 해석 범위

대표는 실제 관측 case이며 그룹 전체의 평균 sequence가 아니다. 각 행은 선택한
기준에 독립적으로 정렬된다. 대상 그룹끼리의 삽입 열은 상호 대응이나 최적 다중
정렬을 주장하지 않는다. 기록 순서를 보존하며 시간·인과·정상 여부를 자동 판정하지
않는다. OCEL은 명시적 case 투영 후 입력한다.

HTML은 사전 계산된 그룹과 후보의 비교 화면이다. 라벨은 Python 그룹 정의 또는
원 case 속성으로 입력하며, 브라우저에서 원 로그 라벨을 수정·저장하는 편집 기능은
이번 범위에 포함하지 않는다. 자원 한도에 걸린 pair는 비용을 추정하지 않고 미계산
상태를 표시한다.
