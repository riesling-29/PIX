# Chevron 방향과 Neutral 표시 검증 — 2026-09-17

이 기록은 Neutral을 선택 옵션으로 도입한 단계의 검증이다. 이후 사용자 승인에 따라 Neutral 가로형을 기본값으로 승격했다. 현재 기본값과 후속 검증은 [기본 스타일 적용 기록](2026-09-17_NEUTRAL_CHEVRON_DEFAULT.md)을 따른다.

## 구현 범위

`render_html`, `export_html`, `export_html_report`에서 다음 인자를 받는다.

```python
export_html(view, "variants.html",
            chevron_orientation="horizontal", chevron_style="neutral")
```

- `chevron_orientation`: `horizontal` 기본값, `vertical`, `auto`.
- `chevron_style`: `classic` 기본값, `neutral`.
- 명시한 방향은 창 너비가 바뀌어도 유지한다. `auto`만 사용 가능한 폭을 보고 다시 배치하며 선택한 이벤트와 검색어를 유지한다.
- Variant 계산과 `pix.visualization.v1` 데이터 계약은 바꾸지 않는다. 같은 문서의 다른 panel에도 Chevron 스타일을 적용하지 않는다.
- 기존 graph 문서는 기본값 외 Chevron 옵션을 거부한다. 잘못된 값은 파일을 쓰기 전에 거부한다.
- Neutral은 작은 이벤트 표식, 외부 활동명, 슬롯 범위선과 선택 시 공유 이벤트 연결선을 사용한다. 객체형은 텍스트로 표시한다.
- 공유 이벤트 연결선은 정체성 표시이며 프로세스 간선이 아니다. 가로 폭·세로 길이는 inclusive precedence slots이며 duration이나 concurrency 증거가 아니다.
- SVG는 방향·스타일, 원본 panel 및 provenance를 보존한다. 표시 설정은 시각화 JSON에 추가하지 않는다.

DFG·OCDFG 무채색 시안의 제품 통합이나 전체 PIX 기능 완성을 뜻하지 않는다. Graphviz 기본값은 유지하며 Chevron은 독립된 PIX 도메인 배치를 사용한다.

## 검증 결과

| 범위 | 결과 |
|---|---:|
| `pytest tests/viewer -q` | 625 passed |
| `node --test tests/viewer/*.cjs` | 249 passed |
| 기존 Graphviz·Chevron 및 visualization 브라우저 회귀 | 21 passed |
| 새 Chevron presentation 실제 Chromium 시나리오 | 5 passed |
| wheel 생성·격리된 설치본 smoke | 211 runtime 파일 일치, 방향·스타일 6조합 통과 |

Ruff는 변경된 Python API·테스트·예제 파일을 통과했다. 새 wheel의 SHA-256은 `04ca6acda62245c50b7a6bc97e31e069be3a34826c01f83c18ee97b68ea3ada5`다. 소스 경로나 `PYTHONPATH`가 개입하지 않는 별도 signed runtime에서 설치본을 import했고, 새 geometry 자산 포함과 잘못된 옵션으로 기존 보고서를 덮어쓰지 않는 동작을 확인했다. [패키지 검증 기록](../../.artifacts/2026-09-17-visualization-chevron-presentation/package/README.md)

브라우저는 Chromium 151.0.7922.34이며, 새 검증은 외부 네트워크 요청을 차단한 상태로 실행했다. 요청·브라우저 오류는 없었다. 새 시나리오의 세부 조건은 다음과 같다.

- 두 스타일 × 두 고정 방향 × 두 화면 폭 × 두 대표 panel에서 이벤트 ID·객체 ID·슬롯·등장 수 보존.
- 자동 모드의 1600→390→1600 너비 변경에서 선택·검색 상태 유지.
- 5/6개의 고유 이벤트와 9/10개의 객체별 appearance 구별, 반복 `Inspect`의 별도 ID 유지.
- SVG 4개를 실제 저장하고 별도로 열어 스타일·방향·metadata 확인.
- 한글·CJK·넓은 라틴 문자·HTML처럼 보이는 문자열에서 텍스트 범위와 원문 보존 확인.
- 기본 데스크톱에서 짧은 `Inspect` 한 줄과 마지막 `Join` 노출, 공유 이벤트 점선과 라벨 비겹침 확인.

검증 중 발견한 고정 10,000 한도 충돌, classic 세로형 축 제목 가림, 문자 수 기반 라벨 넘침, 원본 설명 대체, 공유 이벤트 선의 라벨 관통을 수정했다. 명시적으로 높인 display limit는 geometry에도 전달한다.

## 재현과 산출물

[`examples/chevron_presentation.py`](../../examples/chevron_presentation.py)는 기존 합성 OCEL에서 execution과 variant를 다시 계산해 같은 데이터의 6개 HTML을 생성한다.

```text
python examples/chevron_presentation.py --output .artifacts/2026-09-17-visualization-chevron-presentation --overwrite
```

- 비교 화면: [index.html](../../.artifacts/2026-09-17-visualization-chevron-presentation/index.html)
- 실제 브라우저 검증·소스 해시·스크린샷·SVG: [QA 기록](../../.artifacts/2026-09-17-visualization-chevron-presentation/qa/README.md)
- 회귀 테스트: [Python API](../../tests/viewer/test_chevron_export_options.py), [geometry](../../tests/viewer/test_chevron_geometry.cjs), [실제 브라우저](../../tests/browser/test_chevron_presentation_browser.py).

`.artifacts`는 Git 제외 로컬 산출물이다. 소스와 테스트, 재생성 예제는 버전 관리 대상이다. 이 환경에서는 기존 signed embedded Python과 설치된 Node Playwright를 사용했으며 가상환경 실행 정책을 변경하지 않았다.

## 판단의 한계

위 기능 판단은 2026-09-17의 테스트 대상 소스와 제공된 fixture 범위에서 유효하다. 다른 화면·폰트·데이터에서 겹침, ID 손실 또는 지정 방향 변경이 재현되면 해당 표시 지원 판단을 재검토한다. 작은 합성 로그에서 확인한 결과를 대규모 로그의 성능 보장으로 확대하지 않는다.

작은 표식과 외부 라벨이 기존 큰 회색 Chevron 면보다 DFG 시안과 일관된 인상을 줄 것이라는 디자인 제안이다. 상용 수준의 미감이나 작업 효율 향상은 측정하지 않았으며 알 수 없음이다. 사용자가 슬롯·객체 관계를 더 읽기 어렵다고 판단하면 표시 방식을 재검토하고 `classic`을 유지할 수 있다.
