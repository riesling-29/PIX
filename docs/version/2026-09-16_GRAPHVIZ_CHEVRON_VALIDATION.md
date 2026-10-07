# Graphviz 기본 배치와 OC variant chevron 검증

기준일: **2026-09-16 KST**. 대상은 미출시 PIX 작업본이다. 상태: **구현·최종 통합·독립 설치 검증 통과**. 실제 화면의 사용자 수용 판단은 자동 검사와 별개다.

[변경 요구사항](../requirements/2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md),
[시각화 사용 가이드](../user-guide/VISUALIZATION_GUIDE.md),
[참조별 대체 범위](../requirements/2026-09-15_PIX_VISUALIZATION_UNION.md)를 함께 읽는다.
[앞선 native 시각화 검증](2026-09-15_NATIVE_VISUALIZATION_VALIDATION.md)은 변경 전 기준선으로 유지하며, 그 통과 수를 이번 변경의 검증 수로 재사용하지 않는다.

## 변경한 실행 구조

PIX의 계산·도메인 자료·SVG 상호작용을 유지하면서 **Graphviz를 모든 graph의 기본 배치**로 적용했다. Graphviz 16.0.0을 `@viz-js/viz` 3.30.0 WebAssembly와 함께 동봉한다. Graphviz가 node 위치·spline·label 좌표를 계산하며 PIX가 ID·빈도·단위·근거·출처와 화면을 담당한다. PM4Py/OCPA를 import하거나 해당 라이브러리에 계산을 위임하지 않는다.

| 문서 / 표현 | 기본 | 명시적 대안 |
|---|---|---|
| 신규 `VisualizationDocument`의 graph | Graphviz | `layout_engine="native"` 실험 배치 |
| 기존 `GraphDocument` / `ModelGraphDocument` | Graphviz | `layout_engine="elk"` |
| Matrix / chart / timeline / table | PIX의 해당 panel renderer | graph 배치 설정의 대상이 아님 |
| `ChevronPanel` | PIX의 객체 행·선행관계 슬롯 renderer | Graphviz 좌표와 독립 |

`render_html`, `export_html`, `export_html_report`에서 기본값은 `layout_engine="graphviz"`다. 미지원 조합은 거부하고 배치 실패 시 다른 엔진으로 자동 전환하지 않는다. 시스템 `dot`, Python `graphviz`, Node 또는 CDN은 export된 HTML의 실행 조건이 아니다.

Vendor 기록에는 registry archive·판본·SHA-256·Graphviz source 링크가 포함된다. Viz.js MIT, Graphviz EPL-2.0, Expat MIT license를 함께 배포한다. 배포물 무결성과 런타임 판본 확인은 source에서 같은 binary를 재빌드한 검증과 다르며, source-build 재현성은 미검증이다. [Vendor provenance](../../src/pix/viewer/assets/vendor/graphviz-provenance.json)

## 동일한 DFG·OCDFG의 변경 전후

앞서 사용자가 검토한 네 합성 샘플의 시각화 JSON을 다시 읽어 기본 Graphviz로 export했다. 변경 전후 JSON을 parse한 값이 같음을 확인했으므로 이 비교에서 활동·간선·계수·출처를 바꾸지 않았다. [비교 생성 코드](../../.artifacts/graphviz-2026-09-16/render_comparison.py)

[변경 전후 비교 갤러리](../../.artifacts/graphviz-2026-09-16/comparison/index.html)에서 같은 샘플을 나란히 볼 수 있다. [비교 요약](../../.artifacts/graphviz-2026-09-16/comparison/comparison-summary.json)에 입력 동일성과 측정치를 남겼다.

| 샘플 | Node / edge | 이전 edge-label 겹침 쌍 | Graphviz edge-label 겹침 쌍 | 새 그림 |
|---|---:|---:|---:|---|
| 승인·반려·재작업 DFG | 7 / 8 | 0 | 0 | [PNG](../../.artifacts/graphviz-2026-09-16/comparison/dfg-approval-graph.png) · [HTML](../../.artifacts/graphviz-2026-09-16/comparison/dfg-approval.html) |
| Agent 검증·재시도 DFG | 8 / 11 | 4 | 0 | [PNG](../../.artifacts/graphviz-2026-09-16/comparison/dfg-agent-loop-graph.png) · [HTML](../../.artifacts/graphviz-2026-09-16/comparison/dfg-agent-loop.html) |
| 주문·상품·택배 OCDFG | 8 / 22 | 19 | 0 | [PNG](../../.artifacts/graphviz-2026-09-16/comparison/ocdfg-fulfillment-graph.png) · [HTML](../../.artifacts/graphviz-2026-09-16/comparison/ocdfg-fulfillment.html) |
| Task·Agent·Artifact OCDFG | 7 / 22 | 20 | 0 | [PNG](../../.artifacts/graphviz-2026-09-16/comparison/ocdfg-agents-graph.png) · [HTML](../../.artifacts/graphviz-2026-09-16/comparison/ocdfg-agents.html) |

동일한 브라우저 측정 코드로 exported SVG의 `.pv-edge-label` 경계 상자가 가로·세로 모두 1 CSS pixel보다 많이 겹치는 쌍을 세었다. Node 경계 상자의 겹침 쌍은 변경 전후 모두 0이었다. 간선과 label의 교차, 모든 spline 교차, 전체 미적 품질을 측정한 수치는 아니다. 승인 DFG는 이전에도 label 겹침 0이었으므로 네 샘플 모두에서 같은 수준의 개선이 있었다고 해석하지 않는다.

측정 근거: [이전 DFG](../../.artifacts/graph-quality-2026-09-16/capture-dfg-approval_dfg-agent-loop.json),
[이전 OCDFG](../../.artifacts/graph-quality-2026-09-16/capture-ocdfg-fulfillment_ocdfg-agents.json),
[Graphviz 네 샘플](../../.artifacts/graphviz-2026-09-16/comparison/capture-dfg-approval_dfg-agent-loop_ocdfg-fulfillment_ocdfg-agents.json),
[측정 코드](../../.artifacts/graphviz-2026-09-16/comparison/capture.cjs).

## OC variant chevron 의미와 실제 화면

OCPA의 *Variant Calculation and Layouting*에서 가져온 것은 **객체 instance별 행에서 shared event를 같은 가로 위치로 표현하는 chevron 방식**이다. PIX의 exact qualified-incidence variant 정의는 유지한다. OCPA의 기본 근사 variant 분류와 같은 variant 수·그룹핑을 보장하지 않는다. [OCPA 공식 설명](https://ocpa.readthedocs.io/en/latest/discovery.html)

`build_variant_visualization`은 원 execution 결과와 정확한 variant 결과를 결합한다. Source와 parent computation, 추출의 객체형·qualifier 선택, leading role, membership partition·대표 실행·빈도·모집단을 검사한다. 현재는 `COMPUTED` 결과만 받으며 partial·실패·미해결 tie·불완전한 객체 경로·cycle은 거부한다. 명시적으로 event ID로 해결한 tie는 근거에 공개한다. Canonical labeling을 다시 실행하지 않으므로 수동으로 변조한 payload 그룹핑의 동형성을 새로 증명하지는 않는다.

한 shared event는 하나의 ID와 하나의 inclusive `[start, end]` 슬롯을 갖고 여러 참여 행에 표시된다. Start는 선행관계 DAG의 longest-path 단계, end는 earliest successor 직전 단계이며 sink는 end=start다. 슬롯 폭은 duration·waiting time·빈도가 아니다. 객체형은 색으로 구별하고 동일 타입의 여러 객체도 개별 행을 유지한다. 여러 객체형이 참여한 shared event에는 같은 분할 색을 모든 참여 행에 사용한다.

객체 없는 사건과 boundary-only 사건은 variant 문서의 별도 근거 표에 보존한다. Raw `build_execution_chevrons` helper는 그러한 사건을 포함하면 거부한다. 빈 실행·빈 로그와 표현할 수 없는 근거를 임의의 객체·사건으로 채우지 않는다.

[실행 가능한 예제](../../examples/graphviz_variant_demo.py)는 canonical OCEL을 만든 뒤 native execution 추출·exact variant·OCDFG·OCPN 발견을 실행한다. 세 execution 각각에 Order 1개와 Item 2개가 있고, 그중 두 실행은 같은 variant이며 한 실행에는 재작업이 있다. 화면의 **2/3, 1/3 빈도는 실제 PIX 계산 결과**다. Fork·Join의 공유 사건, 길이가 다른 Item 분기와 합류 전까지 넓어진 Check, 같은 라벨의 서로 다른 사건을 포함한다.

[전체 갤러리](../../.artifacts/graphviz-2026-09-16/demo/index.html),
[재작업 variant](../../.artifacts/graphviz-2026-09-16/qa/variant-chevrons-1.png),
[반복 variant](../../.artifacts/graphviz-2026-09-16/qa/variant-chevrons-2.png),
[공유 사건 선택](../../.artifacts/graphviz-2026-09-16/qa/variant-chevrons-selected-1366.png),
[모바일 Readable](../../.artifacts/graphviz-2026-09-16/qa/variant-chevrons-mobile-readable.png)에서 확인할 수 있다.

## 전용 Chromium 검증

서명된 CPython 3.13.15, 설치된 Node Playwright driver와 Chromium **151.0.7922.34**로 전용 suite를 실행했다. 새 package나 browser 다운로드는 하지 않았다.

```text
PIX_RUN_BROWSER=1 python -m pytest -q tests/browser/test_graphviz_chevron_browser.py
```

전용 실행은 **9 passed / 2.95초**였다. 이는 **7개 UI 시나리오와 2개 추가 검사**이며, 기존 `test_visualization_browser.py`의 12개 browser 회귀와 구별한다. 최종 전체 pytest 수에는 실제 실행한 browser 검사가 포함되므로 따로 더해 전체 통과 수를 부풀리지 않는다.

| 확인 범위 | 관측 결과 |
|---|---|
| 기본 engine | 신규 DFG와 기존 OCDFG·PN·OCPN에서 Graphviz 16.0.0. 기본 문서에 ELK 없음 |
| Legacy 기능 | OCDFG 세 계수와 type filter, OCPN 객체형 filter·initial/final marking 유지 |
| Chevron | shared event 모든 표시의 위치·폭 일치, inclusive 슬롯·늘어난 짧은 분기, instance lane·계산 빈도 유지 |
| 상호작용 | shared-event 그룹 선택·ID/객체 근거, 별도 계산 출처, 검색·SVG 다운로드 |
| SVG | 7개 export를 well-formed SVG로 확인. script·foreignObject·image element 없음 |
| 화면 | Desktop 1600/1366 CSS pixels, mobile 390 pixels; PNG 10개 |
| 네트워크·오류 | 외부 HTTP(S) 요청 0, console/page 오류 0 |
| 소스 일관성 | 전용 browser 실행 전후 viewer source hash 변화 없음 |

[브라우저 실행 기록](../../.artifacts/graphviz-2026-09-16/qa/browser-qa.md)과
[개별 검사·hash·이미지 목록](../../.artifacts/graphviz-2026-09-16/qa/browser-results.json)에 근거를 남겼다.

## 최종 통합 검사

서명된 CPython 3.13.15에서 `PIX_RUN_BROWSER=1`로 전체 pytest를 실행하고 JavaScript geometry·UI·layout suite를 실행했다.

| 검사 | 최종 관측 결과 |
|---|---|
| 전체 pytest | **8,883 passed / 27 skipped / 1,169 subtests passed**, failure 0·error 0 |
| 실제 Chromium 회귀 | **21개 통과**: 기존 12개 + 이번 전용 9개. 위 pytest 통과 수에 포함 |
| JavaScript | **223개 통과**, exit code 0 |
| 실행 중 파일 고정 | source·test·example·tool·vendor **385개 파일 hash 변화 없음** |

전체 pytest 실행 시간은 **51.67초**였다. [최종 JUnit](../../.artifacts/graphviz-2026-09-16/integration-shipped.xml),
[출력](../../.artifacts/graphviz-2026-09-16/integration-shipped.txt),
[요약·hash](../../.artifacts/graphviz-2026-09-16/integration-shipped-summary.json),
[Node 출력](../../.artifacts/graphviz-2026-09-16/node-shipped.txt)에 기록했다.

기존 12개 browser 회귀의 이번 실행 산출물은 [별도 보관한 현재 browser 결과](../../.artifacts/graphviz-2026-09-16/baseline-browser-regression/browser-results.json)와 같은 디렉토리의 캡처에 있다. 변경 전 2026-09-15의 숫자와 이번 재실행을 구별한다.

27개 skip은 로컬 XES corpus opt-in 미선택 11개, PyArrow native runtime 부재 14개, OS symlink 제한 1개, 기존 Python browser 모듈의 `greenlet._greenlet` import 실패에 따른 collection skip 1개다. Skip은 통과 수에 넣지 않았다. 실제 Chromium 21개는 기존 Node Playwright driver를 통해 실행했다. 별도 단계·검토자의 중복 실행 수를 최종 통과 수에 더하지 않는다.

## 최종 wheel·독립 설치 검사

격리한 공식 CPython 3.13.15 환경에서 새 wheel만 로드하여 mining·native·visualization 검사 세 종류를 모두 통과했다. Checkout source나 외부 Python 계산 라이브러리는 설치본 실행 경로에 넣지 않았다.

| 검사 | 관측 결과 |
|---|---|
| Wheel | `pix-0.5.0-py3-none-any.whl`, **1,887,935 bytes** |
| SHA-256 | `072973c300bbb1e013d8d46ad50ba98afebca211c38b13d3855553f3b42e3791` |
| Source → wheel → 설치본 | Runtime **210개 파일 / 6,552,259 bytes** 일치 |
| Native pipeline | 계산 종류 14개, 결과 JSON 왕복 21개, OCEL 3형식, 모델 2종, HTML 3종 통과 |
| 시각화 | Chevron 포함 문서 6종 JSON·HTML 왕복, 필수 파일 19개, UI asset 17개 확인 |
| Vendor | Graphviz/Viz/Expat 배포 파일 4개의 크기·SHA-256 및 license 확인 |
| 배치 선택 | 기본 Graphviz, 명시적 native·legacy ELK, 잘못된 engine/document 조합 2개 거부 |

이 설치 검사는 위 전체 pytest 수와 별도다. [패키지 검사 보고서](../../.artifacts/union-2026-09-15/graphviz-package-smoke.md),
[현 소스 일치 기록](../../.artifacts/union-2026-09-15/package-runtime/graphviz-final/current-source-verification.json),
[설치본 시각화 결과](../../.artifacts/union-2026-09-15/package-runtime/graphviz-final/visualization-smoke/visualization-wheel-evidence.json)에 상세 근거가 있다.

설치본이 export한 case DFG·legacy OCDFG·variant chevron HTML **3개를 실제 Chromium 151.0.7922.34에서 별도로 실행**했다. 실제 Graphviz 16.0.0의 초기화와 cubic 경로, Chevron의 2개 객체 행·5개 사건·7개 표시, 공유 Join의 동일한 위치와 함께 선택되는 두 형상, 짧은 분기의 확장 폭을 확인했다. 브라우저를 offline으로 설정한 상태에서 외부 요청·fetch·page/console 오류는 모두 0이었다. 검사 전후 HTML hash가 설치본 export 기록과 일치했다. PNG 3개와 SVG 2개를 보존했다. 이 3개 설치본 시나리오는 위 pytest 내 Chromium 21개와 별도이며 pytest 통과 수에 더하지 않았다. [설치본 브라우저 증거](../../.artifacts/union-2026-09-15/package-runtime/graphviz-final/installed-browser/installed-browser-evidence.json)

현재 [구현 registry](../requirements/union-2026-09-15/implementation_registry.json)에 이번 통합 QA를 별도 항목으로 추가하고 385개 파일의 snapshot을 갱신했다. `tools/check_mining_registry.py --strict-hashes`는 오류와 stale hash 없이 통과했다. 이는 목록·파일 일관성 검사이며 알고리즘 동등성 증명이 아니다. 이전 mining·native visualization QA와 reference 대체 검증 상태는 유지했다.

## 유효 범위와 재검토 조건

현재의 화면 품질 근거는 네 합성 DFG·OCDFG와 위 bounded execution·모델 사례다. 모든 실무 로그·크기·Graphviz 설정·PM4Py/OCPA variant의 동등성이나 우위를 증명하지 않는다. 대형 실제 OCEL의 최대 처리량·메모리·지연·가독성 우위는 **알 수 없음**이다. 큰 OCPN 전체를 Fit으로 표시하면 긴 generated place ID가 작아지므로 Readable과 pan을 함께 사용해야 한다.

판정은 위 vendor 판본·계약·검사 시점의 소스에 유효하다. 실제 입력에서 ID·참여·계수·단위·출처가 달라지거나 공유 사건의 슬롯이 어긋나면 해당 의미 보존 판단을 철회하고 회귀 사례를 추가한다. 다른 입력에서 심한 label 겹침·간선 혼잡·지연이 확인되면 해당 배치 설정과 표현을 재검토한다. Graphviz 사용 자체를 품질의 영구 보증으로 삼지 않는다.
