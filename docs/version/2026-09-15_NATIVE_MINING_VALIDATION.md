# Native Process Mining 통합 검증 — 2026-09-15

대상은 미출시 PIX 작업본이다. 참조 범위는 고정한 PM4Py 2.7.23.8·OCPA 1.3.4이며,
이번 검증은 PIX의 자체 계산과 저장·설치 경로를 대상으로 한다.
[구조와 정의](../requirements/2026-09-15_PIX_NATIVE_MINING_UNION.md),
[행별 구현 근거](../requirements/union-2026-09-15/implementation_registry.json),
[사용 예](../user-guide/NATIVE_MINING_GUIDE.md)를 함께 읽는다.

## 구현된 구조

`pix.case_centric`은 CaseLog 또는 명시적 case projection을 입력으로 받는다.
발견, 적합성, 통계·성능, 규칙, 모델 변환·검사, feature·학습, 조직 분석,
simulation·streaming·privacy 계산을 하위 모듈로 나눴다.

`pix.object_centric`은 canonical OCEL의 공유 event, 객체형, E2O/O2O와 qualifier,
객체 속성 이력을 받는다. 실행·variant·관계 graph, OCPN/SAW/OCCN,
joint replay·alignment, 성능·규칙, feature·필터·변환·cube, simulation·action 분석을 나눴다.
한 객체형의 flattened replay와 여러 객체를 함께 다루는 joint 계산은 다른 경로다.

계산 결과는 명시적 operator/schema 등록을 통해 저장한다. 원본·부모 계산·모델·설정과
partial/unknown 상태를 함께 남긴다. 변환 계획을 실제 로그로 적용하는 경로는 원본과 근거를
다시 확인한다. XES 속성은 type 구분자를 사용하므로 날짜처럼 생긴 문자열과 실제 날짜를
JSON에서 복원할 때 혼동하지 않는다.

## 전체 회귀 검사

서명된 공식 CPython 3.13.15, pytest 9.1.1로 전체 suite를 실행했다.
저장·복원 회귀 3개를 추가한 최종 실행은
**8,362 passed / 27 skipped / 1,169 subtests passed**, 실패 0건이다.
소요 시간 42.79초는 이 머신에서의 해당 실행값이며 제품 처리 성능 벤치마크가 아니다.

```text
python -m pytest -q --junitxml=.artifacts/union-2026-09-15/integration-final-shipped.xml
```

27개 skip의 이유는 다음과 같다. 건너뛴 검사를 통과로 계산하지 않는다.

| 이유 | 수 |
|---|---:|
| opt-in 로컬 XES corpus suite 미선택 | 11 |
| PyArrow native runtime 부재 | 14 |
| 운영체제가 symlink 생성을 허용하지 않음 | 1 |
| browser suite 수집 건너뜀 | 1 |

새 도메인 코드·결과 codec·model artifact 및 관련 테스트·검증 도구의 Ruff 검사와
format 검사를 통과했다. 별도 read-only 통합 검토에서도 구체적인 결함은 발견하지 못했다.
그 검토의 155개 통과 결과는 전체 suite와 중복되므로 더하지 않는다.

## 실제 계산 결과의 저장·복원

모듈이 실제 반환한 결과를 수집해 JSON 저장 → 복원 → 재저장 후 값·계산 ID·바이트의
일치를 검사했다. 등록된 새 operator **201개 전체(CC 139 / OC 62)**에 실제 호출 근거가 있다.
이 수는 서로 독립적인 알고리즘 201개라는 뜻이 아니다.

| 실행 | 확인한 operator | 대표 결과 검사 | 오류 |
|---|---:|---:|---:|
| 고정 소스 domain capture | 198 | 3,517 | 0 |
| 누락 호출 3개를 포함한 보충 capture | 91 | 155 | 0 |

두 실행의 operator에는 중복이 있으며, 합집합이 201개다. 누적 왕복 검사 3,672회에도
중복 대표 결과가 포함된다. 제품 Python 소스 184개의 hash는 두 실행 사이와 각 실행 중
동일했다. 이 검사는 모든 입력이나 상태 조합을 포괄하지 않는다.

영구 회귀 [test_mining_serialization.py](../../tests/test_mining_serialization.py)의
90개 테스트는 최종 전체 suite에 포함된다. 정수로 주어진 실수 설정, 날짜/문자열,
Boolean/정수, partial/unavailable 결과, Data Petri net과 marking-equation 결과도 검사한다.

## 독립 wheel 설치

표준 setuptools wheel build 후, checkout 밖에서 stdlib와 설치된 PIX만 접근할 수 있는
격리 Python으로 검사했다. PM4Py·OCPA·NumPy·SciPy·Torch 등의 패키지는 없는 환경이다.

| 확인 사항 | 결과 |
|---|---|
| source → wheel → 설치본 바이트 대조 | runtime 파일 191개 일치 |
| Case/OC namespace import | 모듈 82개 성공 |
| `AB, AB, AC` → DFG → IM → PN → alignment | 3개 optimal alignment, 총 비용 0 |
| OCEL 통계 | event 3, object 2, 참여 5 |
| 두 객체의 공유 event 근거 | `e2`, `e3` 보존 |
| 결과 JSON 및 OCEL canonical JSON | 결과 5종과 OCEL 왕복 성공 |

Wheel은 `pix-0.5.0-py3-none-any.whl`, 1,294,308 bytes이며 SHA256은
`b77c002850f11736c122dccbc44f727419366a9ab02b251cb8fe47fc2c89f01b`이다.
이 빌드는 미출시 검증 산출물이며 배포한 release가 아니다.
재현 도구는 [check_mining_wheel.py](../../tools/check_mining_wheel.py)다.

## 실제 로그의 독립 대조

원본을 수정하지 않고 XML/JSON을 직접 세어 PIX 결과와 비교했다.

| 입력 | 확인한 계산 | 결과 |
|---|---|---|
| Activities Daily Living XES.gz 8개 | 원본 순서 DFG, trace/event 수, 결과 JSON 복원 | 148 traces / 11,138 events, 8개 모두 일치 |
| OrderManagement OCEL | event/object 수, qualifier 관계와 고유 E2O 참여 수 | 21,008 events / 10,840 objects / 147,463 관계행 / 147,385 참여쌍 일치 |
| ProcureToPay OCEL | import 진단 및 원본 중복 독립 확인 | 계산 전에 거부됨 |

ProcureToPay 원본에는 동일 객체 안에서 같은 `(attribute name, time)`을 가진 중복 그룹이
242개 있었다. 현재 canonical 계약이 이를 허용하지 않아 `mapping_invalid`로 거부했다.
이 파일은 계산 성공 9개에 포함하지 않으며, 자동으로 값을 선택하거나 원본을 고치지 않았다.
Hospital Billing 전체의 새 계산 벤치마크는 이번 대조에 포함하지 않았다.

## 실행 근거가 부족한 경로와 남은 판단

선택적인 SciPy 실행은 공식 wheel을 검증한 뒤에도 Windows application control이
NumPy의 native extension 로딩을 막아 실행하지 못했다. 외부 LP/MILP 성공 횟수는 0이다.
반면 PIX의 rational simplex와 이를 쓰는 기본 A* 하한 계산은 native 테스트 대상이다.
Transformer adapter 계약은 검사했지만 실제 checkpoint로 추론하는 실행은 하지 않았다.

계산·지원 268개 검토 행 중 `native_profile` 126, `partial` 141,
`external_runtime_unverified` 1로 기록한다. 이는 알고리즘 수나 완료율이 아니다.
일부 variant·입력 모델 클래스·시간 관계·목적함수와 실제 외부 runtime 확인이 남아 있다.
전 참조 variant 대체 검증 완료는 0행이며, 이는 이미 실행한 PIX 계산이 없다는 뜻과 다르다.

소스와 테스트 hash가 이 기록의 유효 시점을 고정한다. 독립 반례, 분모·순서·시간 경계의 오류,
합법 모델 실행 누락, 저장 후 의미 변화, 참조 판본이나 요구 정의 변경이 확인되면 해당 판단을
철회하고 관련 행을 다시 검토한다. 생산 규모의 일반적 시간·메모리 한계와 Agent 최초 작업
성공률은 **알 수 없음**이다.

## 로컬 실행 근거

다음 파일은 `.artifacts/union-2026-09-15/` 아래의 로컬 검사 산출물이다.
공개 소스에서 재현할 수 있도록 테스트와 검증 도구는 별도로 유지한다.

- `integration-final-shipped.xml`: 최종 전체 pytest 결과. 이전 `integration-final.xml`은
  회귀 3개를 추가하기 전의 통합 검사다.
- `codec-audit.md`: 실제 계산 결과 저장·복원 검사와 수정 이력.
- `package-smoke.md`, `package-runtime/final-01/`: 격리 설치와 source hash 근거.
- `corpus-mining-evidence.json`, `p2p-import-diagnostics.json`: 실제 로그와 원본 대조.
- `solver-runtime-provenance.json`: 선택적인 수치 runtime 검증 및 로딩 제한 근거.
