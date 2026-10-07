# Native visualization 통합 검증

작업 식별일: 2026-09-15. 최종 확인일: **2026-09-16 KST**.

대상은 미출시 PIX 작업본이다. 참조 범위는 고정한 PM4Py 2.7.23.8·OCPA 1.3.4다.
[시각화 대체표와 설계 판단](../requirements/2026-09-15_PIX_VISUALIZATION_UNION.md),
[사용 가이드](../user-guide/VISUALIZATION_GUIDE.md),
[앞선 계산 엔진 검증](2026-09-15_NATIVE_MINING_VALIDATION.md)을 함께 읽는다.

## 실행 구조

`CaseLog / canonical OCEL → PIX 계산·모델 → 도메인 어댑터 → VisualizationDocument
→ PIX 배치 → SVG/HTML` 경로를 구현했다. 계산과 화면을 분리하며, 화면에서 발견·재생·
alignment·KDE를 다시 수행하지 않는다. 새 문서는 Graphviz나 ELK를 실행하지 않는다.
기존 `GraphDocument`·`ModelGraphDocument`는 기존의 패키지 내 ELK 경로를 유지한다.

| 영역 | 화면에 연결한 범위 |
|---|---|
| Case-centric | DFG, PN, process tree, POWL, Split BPMN, heuristics net, transition system, footprints, replay/alignment, 조직 관계, 통계·성능·시간·제약 |
| Object-centric | OCDFG, OCPN, OCCN, SAW-net, 객체·객체형 관계, execution·variant 근거, joint replay/alignment, 제약·성능·속성 이력 |
| 공통 화면 | graph, matrix, chart, timeline, table; 검색·선택·확대·이동·범례·근거 inspector |
| 내보내기 | 외부 요청 없는 HTML, 다시 읽을 수 있는 시각화 JSON, 브라우저 SVG 다운로드 |

모델 14종과 알려진 발견·변환 결과형을 명시적으로 연결한다. 지원하지 않는 객체를
임의의 표로 바꿔 지원되는 것처럼 표시하지 않는다. `build_visualization`은 여러 결과를
독립 패널로 묶고, 명시적 모델 주석·footprint 비교·variant duration 결합은 별도 helper가
모델·원본·모집단을 확인한다.

출처는 계산 ID, 원본·모델 digest, 요청 조건, 상태에 더해 `panel_ids`와 `input_path`를
보존한다. 중첩 문서에서도 출처의 패널 소유권이 유지된다. 연결된 패널이 없는 실패 입력을
문서 전체 출처로 확대하지 않는다. Inspector는 해당 패널의 출처를 표시하고 JSON/SVG
metadata는 전체 출처를 보존한다.

## 최종 실행 결과

서명된 공식 CPython 3.13.15에서 `PIX_RUN_BROWSER=1`로 전체 suite를 실행했다.

| 검사 | 최종 관측 결과 |
|---|---|
| 전체 pytest | **8,818 passed / 27 skipped / 1,169 subtests passed**, 실패·오류 0 |
| 실제 Chromium 회귀 | **12개 통과**, 위 pytest 전체 수에 포함 |
| JavaScript geometry·UI·기존 layout | **161개 통과**, 실패 0 |
| 실행 중 소스·테스트·예제·도구 hash | **370개 파일 변화 없음** |

전체 pytest 실행 시간은 47.98초였다.
[최종 JUnit](../../.artifacts/visualization-2026-09-15/integration-shipped.xml),
[요약·파일 hash](../../.artifacts/visualization-2026-09-15/integration-shipped-summary.json),
[Node 출력](../../.artifacts/visualization-2026-09-15/node-shipped.txt)에 기록했다.

27개 skip은 통과 수에 포함하지 않는다. 로컬 XES corpus opt-in 미선택 11개,
PyArrow native runtime 부재 14개, OS symlink 제한 1개, 기존 Python browser 모듈의
`greenlet._greenlet` import 불가에 따른 collection skip 1개다. 새 native browser
suite는 기존 Node Playwright driver를 사용해 실제 Chromium에서 실행했다.

Ruff check와 format check를 통과했다. 도메인별·검토자별 실행 수는 전체 suite와
중복되므로 합산하지 않는다. 테스트 실행 시간은 이 머신의 한 번의 관측값이며 제품
처리량이나 사용자 데이터에서의 성능을 뜻하지 않는다.

## 실제 화면 검증

[예제 생성기](../../examples/native_visualization_demo.py)는 PIX의 실제 계산 결과를
사용하는 분석 페이지 12개와 명시적으로 구분한 fixture·empty·partial 페이지 3개를 만든다.
[생성된 gallery](../../.artifacts/visualization-2026-09-15/demo/index.html)에서 볼 수 있다.
재현 명령과 사용할 API는 사용 가이드에 있다. `.artifacts`는 로컬 검증 산출물이므로
다른 checkout에서는 예제 생성기로 다시 만든다.

실제 Chromium 151.0.7922.34에서 데스크톱 1,366px와 작은 화면 390px를 검사했다.
활동·객체·전이 ID와 간선 수, 다섯 panel 종류, 탭 전환, 검색, 확대·이동·Fit·Readable,
키보드 선택, SVG 다운로드를 확인했다. hostile label은 실행되지 않는 텍스트로 남았고,
큰 정수의 브라우저 반올림은 명시적으로 거부했다. unknown은 0으로 바뀌지 않았다.

패널 66개를 방문하고 캡처 27개를 남겼다. 외부 HTTP(S) 요청 0건, console/page error
0건이다. 상세 근거는 [browser QA](../../.artifacts/visualization-2026-09-15/browser-qa.md)와
[실행 JSON](../../.artifacts/visualization-2026-09-15/browser/browser-results.json)에 있다.

## 설치된 패키지 검사

새 wheel을 별도 디렉터리에 설치한 뒤 checkout 밖에서 PIX만 접근 가능한 Python으로
검사했다. PM4Py·OCPA를 import하거나 계산 엔진으로 실행하지 않았다.

| 확인 사항 | 결과 |
|---|---|
| source → wheel → 설치본 바이트 일치 | runtime 파일 202개, 5,150,087 bytes, 불일치 0개 |
| Case/OC namespace | 모듈 82개 import 및 실제 계산 smoke 통과 |
| 새 시각화 입력 | DFG, raw OCEL, process tree, ModelArtifact, 발견 결과 wrapper의 JSON·HTML 통과 |
| 출처 결합 | 단순 합성, 중첩 합성, 패널 없는 실패 입력과 정상 sibling의 JSON·HTML 보존 통과 |
| 기존 경로 | legacy OCDFG HTML 및 ELK asset·license 유지 확인 |

`pix-0.5.0-py3-none-any.whl`은 1,381,752 bytes이며 SHA256은
`da5c2cf315f9e30b559de3e4407c0da33b24b1aaf525a15cef174b4d4020fbeb`이다.
이는 검증용 빌드이며 공개 release를 배포한 것이 아니다.
[패키지 검증 기록](../../.artifacts/union-2026-09-15/package-smoke.md)에서
최종 `visual-final-fixed`와 수정 전 이력을 구분한다.

## 의미 보존과 검증 한계

최종 통합 검토에서 발견한 Case→OCEL 변환 wrapper의 공개 API 연결 오류와,
합성·중첩 문서에서 출처의 패널 소유권이 사라지는 오류를 수정했다. 패널 없는 실패 입력의
출처가 정상 결과에 연결되는 경계도 회귀 테스트에 포함했다. 검토에서 보고한 미해결
finding은 없지만, 이것이 모든 입력에서 오류가 없다는 증거는 아니다.

시각화 대체표의 26행은 **검토 단위**다. DFG cost/performance overlay의 전체 옵션,
완전한 BPMN 표기, 임의 attribute dotted-chart 설정, log-x 축, 대표 OC variant chevron,
전체 dual-DFG interleaving overlay 등은 남아 있다. 프로그램 API의 PNG/PDF 출력은
이번 구현 범위에 없다. upstream의 모든 옵션·출력과 동등함을 검증하지 않았다.

앞선 계산 대체표도 268행 중 native profile 126행, 부분 구현 141행,
외부 runtime 미검증 1행이다. 모든 행에 연결 경로가 있다는 사실과 참조 알고리즘의 모든
variant를 대체했다는 주장은 다르다. `reference_replacement_verified`는 모두 false다.

현재 화면 한도는 graph 1,500 nodes / 6,000 edges이며 force 배치는 1,000 nodes다.
이는 검증된 최대 처리량이 아니다. 대형 실제 로그의 쾌적한 처리 크기, 다른 renderer 대비
속도와 가독성 우위는 **알 수 없음**이다.

이 검증은 기록된 소스 hash·입력·브라우저·실행 환경에 한정해 유효하다. 소스나 계약이
바뀌거나, 대상 로그에서 공유 사건·비용·단위·출처가 손실되는 반례가 나오면 해당 판단을
철회하고 재검증한다. 실제 업무 화면에서 교차·겹침·선택 지연이 수용되지 않으면 자체
배치의 기본 채택도 재검토한다.
