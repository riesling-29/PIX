# 승인된 Neutral Chevron 기본 적용 — 2026-09-17

이 기록의 wheel·파일 수는 W4 추가 전 Chevron 검증 snapshot이다.
2026-09-18 모델·W4 통합본의 전체 테스트와 새 wheel 검증은
[통합 보고서](../reports/2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md#11-통합-검증과-재현)를 따른다.

## 현재 동작

사용자가 승인한 작은 이벤트 표식·바깥 활동명·슬롯 범위선 스타일을 실제 기본 출력으로 적용했다. 이전 단계의 선택 옵션 구현과 달리, 스타일 인자가 없는 호출에도 적용된다.

```python
from pix.viewer import export_html

export_html(view, "layout.html")  # neutral, horizontal
export_html(view, "vertical.html", chevron_orientation="vertical")
export_html(view, "responsive.html", chevron_orientation="auto")
export_html(view, "classic.html", chevron_style="classic")
```

`render_html`, `export_html`, `export_html_report`, JavaScript mount 및 Chevron geometry 기본값을 일치시켰다. 가로·세로 명시 방향은 고정하고 `auto`만 화면 폭에 따라 전환한다. 기존 컬러 Chevron은 `classic`으로 선택한다.

Variant 계산, inclusive 슬롯, event/object ID, 공유 이벤트 관계와 원본 근거는 유지한다. Graphviz 기본 graph 배치도 유지하며, 이 변경은 Chevron 표현에 적용한다. 기존 GraphDocument/ModelGraphDocument는 Chevron이 없으므로 유효한 스타일 값 두 가지 모두 기존과 동일한 HTML을 출력한다. 이 문서들에 세로·자동 Chevron 방향을 지정하면 거부한다. 잘못된 옵션 값은 저장 전에 거부한다.

이미 저장된 HTML은 렌더러를 자체 포함하므로 다시 생성해야 현재 기본값을 사용한다. 기존 디자인 시안과 검증 기록은 보존했다.

## 이번 소스의 검증

| 검증 | 결과 |
|---|---:|
| `pytest tests/viewer -q` | 707 passed |
| `node --test tests/viewer/*.cjs` | 249 passed |
| 실제 Chromium 회귀 시나리오 | 26 passed |
| 격리된 wheel 설치본 | runtime 파일 211개 일치, 기본 API 3개 및 명시적 6조합 통과 |

브라우저는 Chromium 151.0.7922.34다. 기본값 출력, 고정/자동 방향, 공유 이벤트 선택과 검색 유지, 실제 SVG 저장과 독립 렌더링, 다국어 라벨, classic 슬롯·색상 호환성을 검사했다. 외부 요청·브라우저 오류·검증 중 소스 변경은 없었다. 기본 출력에서도 두 대표 Variant의 9/10 appearances와 원본 ID·슬롯·metadata를 확인했다.

새 wheel SHA-256은 `e32b95ef7dbdbb84ba671bf52c89396f4f02b7561a4ff5c29693e6056d8f340a`다. 소스 경로 없는 signed Python 실행 환경에서 설치본의 기본 스타일·방향, classic 선택, 옵션 오류 시 기존 파일 보존을 검증했다. 관련 Python 변경의 Ruff와 `git diff --check`도 통과했다.

## 확인 파일

- [옵션 없는 실제 기본 출력](../../.artifacts/2026-09-17-visualization-chevron-presentation/default.html)
- [기본 출력 및 방향·스타일 비교](../../.artifacts/2026-09-17-visualization-chevron-presentation/index.html)
- [브라우저 검증 기록](../../.artifacts/2026-09-17-validation-neutral-chevron-default/README.md)
- [wheel 검증 기록](../../.artifacts/2026-09-17-validation-neutral-chevron-default/package/README.md)
- [사용 가이드](../user-guide/VISUALIZATION_GUIDE.md)
- [재생성 예제](../../examples/chevron_presentation.py)
- [이전 선택 옵션 도입 기록](2026-09-17_CHEVRON_PRESENTATION_VALIDATION.md)

`.artifacts`는 로컬 검증 산출물이며 Git 제외 대상이다. 예제로 기본 출력 1개와 명시적 옵션 출력 6개를 다시 만들 수 있다. 이번 기능 확인은 2026-09-17 소스와 테스트 범위에서 유효하다. 다른 데이터에서 ID·슬롯 손실, 지정 방향 변경 또는 라벨 겹침이 재현되면 해당 지원 판단을 재검토한다. 대규모 로그 성능이나 미감의 정량적 우위는 이번 검증 범위가 아니다.
