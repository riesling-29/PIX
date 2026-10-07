PIX 자체 계산 엔진 — 실행 가능한 코드 제안
=========================================

작성일: 2026-09-09. 상태: 제품 통합 전 검토용 코드. PM4Py·OCPA 계산을 호출하지 않는다.

이 초안은 기존 PIX 0.2.0의 OCEL·builder·validator·canonical digest를 사용한다. 별도 canonical 모델을 만들지 않는다. 제품의 `src/pix`와 설치 설정에는 반영하지 않았으며, 이 폴더는 배포 패키지에 포함되지 않는다. 전체 PM4Py/OCPA 알고리즘 대체 구현을 완료했다는 의미도 아니다.

도메인 구조와 검토할 계산 정의는 [자체 Process Mining 구조 검토](../../architecture/3_PIX_NATIVE_PROCESS_MINING_STRUCTURE_REVIEW.md)를 먼저 읽을 수 있다. 입출력 기준은 [입출력·자체 엔진 제안](../../architecture/2_PIX_OCEL_IO_AND_INTEROPERABILITY_PROPOSAL.md)에 연결된다.

**실제로 동작하는 범위**

| 파일 | 책임 | 제품 통합 시 배치 후보 |
|---|---|---|
| [compute.py](pix_native_proposal/compute.py) | validated context/index, 객체별 trace, 객체별 directly-follows, 근거와 계산 식별자 | 계산 구현은 `pix.compute`; 입출력 계약은 표준 라이브러리만 쓰는 `pix.contracts`로 분리 |
| [io.py](pix_native_proposal/io.py) | OCEL 2.0 JSON·SQLite export, 재수입 검증, 출력 실패 근거 | `pix.ocel.export`와 형식별 serializer |
| [engine.py](pix_native_proposal/engine.py) | 명시적으로 요청한 자체 연산 실행, 검증된 context 재사용 | `pix.engine`, 공개 facade는 `pix.api` |
| [result_json.py](pix_native_proposal/result_json.py) | 분석 결과의 versioned JSON 출력 | 결과 전용 serializer. OCEL serializer와 구별 |
| [demo.py](demo.py) | 로그 → 표준 export → 자체 trace/DFG → 결과 JSON 예시 | 사용자 안내용 예제 |

`compute.py`는 검토 편의를 위해 계약과 연산을 한 파일에 두었다. 그대로 통째로 `pix.contracts`에 옮기면 안 된다. 기존 경계 검사는 contracts에 표준 라이브러리만 허용하고 intelligence가 compute를 import하지 못하도록 한다. 통합할 때 `TraceSpec`, 결과 envelope, graph/trace payload, 근거 record는 별도 계약으로 분리한다. 현재 결과에서 재사용하는 OCEL `E2O`도 세 문자열의 immutable relation-evidence 계약으로 옮겨, 해석 계층이 compute/ocel 구현에 의존하지 않도록 한다.

**코드 사용 형태**

아래 API는 이 제안 폴더에서만 실행 가능하다. `pix.compute()`나 `pix.ocel.export_ocel()`로 제품에 추가된 상태가 아니다.

```python
from pix.ocel import read_ocel
from pix_native_proposal.compute import TraceSpec
from pix_native_proposal.engine import DFGRequest, TraceRequest, compute
from pix_native_proposal.io import export_ocel
from pix_native_proposal.result_json import result_json_bytes

log = read_ocel("orders.json")
spec = TraceSpec(object_type="order", qualifiers=None, tie_policy="reject")

traces, graph = compute(
    log,
    requests=(TraceRequest(spec), DFGRequest(spec)),
)
export = export_ocel(log, "orders.sqlite", format="ocel20-sqlite")
graph_document = result_json_bytes(graph)
```

trace는 object별로 구성한다. 공유 event는 각 object trace에 한 번씩 나타나며, 같은 event/object의 복수 qualifier 때문에 발생 횟수를 늘리지 않는다. 선택된 qualifier의 관계 근거는 모두 남긴다. O2O로 event를 다른 object에 전파하지 않는다. 이러한 전파나 process-execution 추출은 별도의 정의가 필요한 연산이다.

현재 DFG의 edge 발생 횟수는 `(source event, target event, object)` 근거 record 수이다. 완전한 OCDFG, 인과관계, process execution, variant, OCPN discovery를 구현한 것으로 표시하지 않는다. 활동마다 event occurrence와 distinct event ID를 함께 제공하고, edge마다 원본 event/object 관계를 제공한다.

`qualifiers=None`은 모든 qualifier, 빈 tuple은 아무 관계도 선택하지 않음, `("",)`는 빈 문자열 qualifier만 선택함을 뜻한다. 미사용 선언 type은 빈 결과를 계산할 수 있지만, 선언되지 않은 type은 `unavailable`이다. 같은 객체에 속한 두 event의 UTC 시각이 같으면 기본적으로 `unavailable`; `event_id` 동률 정책은 명시적으로 선택하는 사전식 선형화이다. 그 순서를 관측된 인과관계로 해석하지 않는다.

유효한 입력에서 computation identity는 source canonical digest, operator ID/version, 관점 조건에 의해 정해진다. 결과를 cache하는 기능은 이 초안에 없다. 식별자 형식은 제안 버전이며 향후 모델 입력·seed·새 parameter를 추가할 때 함께 정의해야 한다. invalid source에는 정상 dataset/computation identity를 부여하지 않는다.

export는 정규화·의미 검증 후 임시 파일에 출력하고 기존 PIX reader로 재수입해 digest 동일성을 확인한 뒤 게시한다. `overwrite=False`이며 기존 파일이 생기는 경쟁 상황도 덮어쓰지 않는다. 실패는 `ExportError`로 진단하며 파일을 일부만 출력하고 성공 처리하지 않는다. `reference_schema="not_run"`은 공식 schema 검증을 하지 않았다는 실제 상태이다.

**검증**

2026-09-09, Windows의 CPython 3.11.15에서 이 폴더의 **39개 unittest가 통과**했다. 두 명의 구현 담당자가 서로의 코드를 읽고 발견한 Unicode parameter와 UTC overflow 예외 문제를 수정한 뒤 통합 실행했다. `demo.py`도 JSON·SQLite 왕복과 자체 계산 결과 출력을 완료했다.

```powershell
& 'C:\Users\migeo\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe' -B `
  'D:\ChantaResearchGroup\PIX\docs\proposals\native_core_v1\run_checks.py'

& 'C:\Users\migeo\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe' -B `
  'D:\ChantaResearchGroup\PIX\docs\proposals\native_core_v1\demo.py'
```

runner와 demo는 현재 process의 import 경로만 설정하므로 패키지 설치가 필요 없다. 테스트 출력 파일은 각각 TemporaryDirectory에 생성된다.

검증 사례는 다음과 같다.

- 공유 event로 인한 가짜 cross-object edge 부재, 복수 qualifier의 중복 집계 방지, 고립 객체·singleton·미사용 type 보존.
- timestamp 동률 거절과 명시적 선형화, UTC offset 동치, microsecond 차이, 입력 순열에 대한 결정성.
- JSON·SQLite의 다섯 primitive, object history와 최초 비-epoch 시점, E2O/O2O qualifier 보존.
- 출력 digest 불일치, unsupported format, 정수 범위 초과, 기존 파일·동시 생성, 정규화 실패 시 게시 차단.
- 도메인 검토 예시의 event pair/객체 발생 집계 차이와 event graph가 객체의 전역 identity 차이를 숨기는 사례.

이는 제안 코드의 소형 계약 시험이며 전체 PIX 회귀 suite, 모든 OCEL producer, 전체 upstream 알고리즘, 대용량 성능을 검증한 결과는 아니다. 성능 한계·전체 구현 공수는 알 수 없음이다.

**제품 통합 전에 필요한 변경**

1. 기존 reader의 중복 JSON member, XML 미인식 경로, SQLite missing-source 관계, 지원 정밀도 초과 timestamp 처리부터 보강한다. 이 초안의 exporter가 만든 파일에 대한 왕복 성공은 임의 외부 입력의 안전한 수용을 증명하지 않는다.
2. 결과 계약과 계산 구현을 기존 계층 경계에 맞게 분리하고, 공개 API 이름·오류 계약을 확정한다. 생산 코드로 옮길 때 기존 import-boundary 검사와 canonical golden vector를 수행한다.
3. XML은 relation dialect·namespace·경로 검증 profile을 먼저 확정한 뒤 추가한다. 이 초안의 XML/gzip export는 명시적 unsupported이다.
4. SQLite는 int64 초과 정수·negative zero, 예약 열·ASCII 대소문자 충돌·NUL을 거절한다. 이 입력을 지원하려면 별도의 표현 계약이 필요하다. 임의 coercion으로 해결하지 않는다.
5. 결과 JSON은 출력용 제안이다. model/result import와 schema validator, Petri net/OCPN 실행 의미, process-execution/variant/적합성 검사는 후속 범위이다.

기존 reader에 대한 최소 수정 위치는 다음과 같다. 이는 적용되지 않은 코드 제안이다.

| 대상 | 변경 모양 | 기존 결과 계약에서의 분류 |
|---|---|---|
| JSON | `json.load`에 중복 member를 거절하는 `object_pairs_hook` 추가. 동일 값 중복도 거절 | `schema_invalid`, candidate 없음 |
| XML | start/end의 전체 경로·namespace·허용 속성·cardinality를 검사하고, 승인된 record 경로만 조립 | `schema_invalid`; 공식 XSD 검사와 별도 profile |
| SQLite | 관계 source가 조립된 event/object에 전부 존재하는지 검사한 뒤 반환 | 단기 `mapping_invalid`; 장기 독립 relation 중간표현으로 invalid candidate 보존 |
| timestamp | ISO parse 성공 경로에서 6자리 이후 비zero fraction 차단. `.123456000`은 허용 | `mapping_invalid` |

국소 helper의 예시는 다음과 같다. `schema_failure`/`mapping_failure`는 현재 `ingest/formats/common.py`의 기존 예외 helper를 사용한다.

```python
def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise schema_failure(
                "duplicate_json_member", f"Repeated member: {key}", (key,),
            )
        result[key] = value
    return result

def require_microsecond_precision(text, at):
    for match in re.finditer(r"[.,]([0-9]+)", text):
        if any(digit != "0" for digit in match.group(1)[6:]):
            raise mapping_failure(
                "timestamp_precision_loss",
                "Canonical V1 cannot preserve this timestamp precision.",
                at,
            )
```

JSON hook의 위치는 member 이름만 알 수 있고 완전한 JSON path가 아니다. 시간 helper는 ISO parse 성공 뒤 호출하는 지원 정밀도 검사이며 RFC3339 전체 validator가 아니다. XML은 허용 태그 이름 집합만 검사해서는 잘못된 경로·namespace를 막을 수 없으므로 이 두 helper와 같은 크기의 수정으로 취급하지 않는다.

현재 코드 제안의 유효 범위는 PIX 0.2.0의 현행 계약과 위 시험 사례이다. 계약 변경이나 반례가 나오면 해당 의미 보존·정확성 주장을 재검토한다. 실용적인 첫 통합 단위는 **입출력·공유 계산 입력·객체별 trace/DFG·근거 있는 결과**이며, 이후 알고리즘군을 같은 검증 방식으로 추가하는 안이다.
