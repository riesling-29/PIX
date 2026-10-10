# PIX variant catalog 구현·Schumpeter 인계

작업 기준: main `2c74f0c4cca1a6eb2a0a9af36990ef7b379467c3`, work `b343a5bee613ec243848432c98a4e51843c9e17a`.
작업 브랜치: `work-variant-catalog-20261010`, [PR #8](https://github.com/Chanta-Research-Group/PIX/pull/8).
최종 통합 SHA와 실행 상태는 PR/Git 기록을 따른다.

## 범위와 계약

20%는 사용자가 확정한 **고유 variant 개수의 상위 20%**다. 그룹별 V에 대해
ceil(V*p/100)개를 고르고 빈도 동률은 활동 tuple 사전순이다. case coverage는 별도다.
P00/P02/P04 문서·예제·인계, F01/F02 빈도 목록·복수 sequence·선택 저장/복원·SVG를 추가했다.
P01은 기존 work의 대표 비교와 함께 통합한다. 새 대표 선정 규칙은 추가하지 않았다.

CaseLog + TraceGroup/라벨 + CaseTraceSpec을 사용한다. 활동 순서·반복·빈 trace,
unassigned를 보존하며 빈 그룹 비율은 N/A다. 원본 누락을 빈 trace로 바꾸지 않는다.
검색과 그룹 표시만으로 분모·원 frequency·선택을 바꾸지 않는다. 기존 비교와
정확한 활동 tuple 그룹화를 공유한다. OC 구조 exact variants와는 별개다.
원 source digest, computation identity, 실제 case/event IDs를 보존하고 codec으로 왕복한다.
catalog_id는 source·계산·payload에 결합하며 다른 데이터/profile의 선택을 거부한다.

## 실행 근거

복구본 로컬 Linux Python 3.12.14: **10,626 passed, 54 skipped, 1,169 subtests passed**.
계산·comparison·codec 집중 검사 145 passed. 설치 wheel의 mining/visualization 두 검사 통과.
Ruff·JS 문법·diff whitespace 검사 통과. 환경 재시작 전 결과는 복구본 증거에 합산하지 않았다.

CI는 Linux 3.10/3.12, Windows 3.13, macOS 3.13 전체 회귀와 격리 wheel,
별도 Node 및 실제 Chromium 검사를 실행한다. 첫 실행에서 catalog의 7개 실제 흐름은
통과했고, 기존 간선 라벨 클릭 영역 결함을 발견해 수정했다. 실제 스크린샷 검토에서는
중복 진단 수백 줄이 화면을 밀어내는 문제를 확인해 동일 문구를 횟수로 요약했다.
원본 진단의 occurrence/위치는 metadata·계산 JSON에 그대로 보존한다.
Windows 전체 회귀는 통과했지만 vendor 라이선스의 checkout 줄바꿈 변환으로 wheel provenance hash가 달라졌다. vendor 파일의 원본 bytes 보존을 Git 속성으로 고정했다. 최종 CI 결과는 아래에 갱신한다. workflow 존재만으로 통과를 뜻하지 않는다.

## 재현과 소비

```bash
python -m pip install -e '.[dev,imports]' build
python examples/trace_group_comparison_demo.py
python examples/trace_variant_catalog_demo.py
python -m pytest -q
python -m build --wheel
python tools/validate_usage_wheel.py --wheel dist/pix-0.5.0-py3-none-any.whl --output .artifacts/wheel
```

wheel smoke는 체크아웃 밖의 pip 없는 독립 환경에 wheel과 선언된 runtime 의존성만
설치하고 `python -I`로 실행한다. 원본·wheel·설치 파일의 SHA-256을 비교한다.
CI artifact의 JSON에 commit별 환경·wheel hash·pipeline 결과를 보관한다.

Schumpeter는 `catalog_trace_variants`/`compare_trace_groups`의 구조화된 결과를
소비한다. computed/partial/unavailable/invalid_input 및 issues를 먼저 읽고 payload
부재를 빈 성공으로 바꾸지 않는다. source digest, computation_id, case/event IDs와
명시 투영 receipt를 전달한다. 입력 수집·LLM·도구 실행·재시도·운영 저장은 Schumpeter,
계산과 근거는 PIX 책임이다. 의존 방향은 Schumpeter → PIX다.
새 adapter 설계 전 Schumpeter의 최신 코드와 기존 연동 경로를 확인한다.

## 잔여

- 차이 표시·조작 편의성은 실제 업무 데이터로 사용하면서 평가한다.
- F03 브라우저 라벨 편집은 필요 확인 후 진행한다.
- H01 새 대표·공통 노드 선정과 H02 ILP는 보류한다.
- V01 기존 입력 감사 150개 잔여, OPERA arc·flooding·OCEL 판본 대조는 유지한다.
- V02/V03 전체 OCPM 의미·한도·규모 감사, V04 참조 대체·독립 출시는 후속이다.
- 이번 검증으로 전체 PM4Py/OCPA 대체나 도메인 수락 완료를 주장하지 않는다.
