"""Reproduce the dated replacement-profile assessment; not a parity certificate.

Classification decisions are review judgments, not measured percentages within
a partially implemented algorithm. Historical registries are never modified.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/reports/completion-2026-09-18"
SCOPE = "docs/requirements/scope-01/replacement_registry.json"
UNION = "docs/requirements/union-2026-09-15/implementation_registry.json"
W4 = "docs/requirements/models-w4-2026-09-17/implementation_registry.json"
VIEW = "docs/requirements/2026-09-15_PIX_VISUALIZATION_UNION.md"
VALIDATION = "docs/reports/2026-09-17_MODELS_AND_W4_IMPLEMENTATION_REPORT.md"

LABELS = {
    "profile": "명시 profile 구현",
    "partial": "부분 지원",
    "external_runtime_unverified": "외부 runtime 미검증",
    "absent": "대응 경로 미확인",
}

# Only the specific missing capability below is considered closed. This is not
# promotion to full reference parity, nor an approval by the domain expert.
PROMOTIONS = {
    "PM-MODEL-003": "독립 StochasticPetriNet 자료형·파라미터 출처·저장 및 발화 경로 추가. 범용 GSPN 분석은 별개.",
    "PM-MODEL-005": "기존 일반 tree→PN에 transition-bordered 변환과 독립 언어 검산 추가. 지원 tree operator 범위.",
    "PM-MODEL-021": "지원 5개 모델군의 occurrence별 활동명 읽기·변경·출처 추가. 모든 모델형/NetworkX 호환은 아님.",
    "PM-ADV-002": "관측 cutoff와 완료/검열을 구분하는 prefix dataset 추가. 다중 landmark/as-of 속성 join은 별개.",
    "PM-ADV-011": "다음 활동 target에 관측·미관측·완료/검열 근거 추가. 학습된 classifier 자체가 아님.",
    "PM-ADV-012": "다음 event 시간·remaining time target과 외부 완료/검열 근거 추가. upstream 기본값 동등성은 미검증.",
    "OC-MODEL-002": "객체형별 source-target directed-walk subprocess와 경계/marking 손실 근거 추가.",
    "OC-MODEL-003": "project→restrict→hide→reduce 조합 경로 추가. 잘린 동기화의 보존을 보장하지 않으며 감소 규칙 전체 지원은 별개.",
    "OC-FEAT-007": "timestamp-block k-step sample/target 생성 추가. timestamp/execution identity가 있는 feature 행의 profile.",
    "OC-FEAT-009": "역변환·native 선형회귀 fit/predict·held-out MAE 추가. 비선형 모델이나 임의 estimator 호환은 아님.",
    "OC-ACT-004": "검증 replay prefix의 marking에서 객체 모집단을 추론. 벽시계 시각/실제 물리 상태/인과효과와 구분.",
}

# Map the 26 visualization review families into the original 21 SCOPE rows.
# Several families may map to one row; the original row is counted only once.
VIEWS = {
    "PM-VIEW-001": (
        "partial",
        ["V-CC-01"],
        "빈도 DFG 지원; 일반 performance/cost/timeline overlay 미완성",
    ),
    "PM-VIEW-002": (
        "partial",
        ["V-CC-02"],
        "PN·replay/alignment 주석 지원; 모든 성능/greedy decoration 미완성",
    ),
    "PM-VIEW-003": (
        "partial",
        ["V-OC-01"],
        "OCDFG 빈도·객체형·근거 지원; 일반 성능 overlay 미완성",
    ),
    "PM-VIEW-004": (
        "partial",
        ["V-OC-02"],
        "OCPN·지원 timed-token mean 주석; 모든 OPERA/배치/지표 variant 미검증",
    ),
    "PM-VIEW-005": (
        "partial",
        ["V-CC-03"],
        "Tree operator/occurrence 지원; node frequency annotation 전체 미완성",
    ),
    "PM-VIEW-006": (
        "partial",
        ["V-CC-04"],
        "제한 BPMN 지원; pool/message/boundary 등 미지원",
    ),
    "PM-VIEW-007": (
        "partial",
        ["V-CC-05"],
        "POWL 부분순서 지원; BASIC/NET 전체 표기 대응 미완성",
    ),
    "PM-VIEW-008": (
        "profile",
        ["V-CC-06"],
        "Dependency와 AND binding 및 근거를 표현하는 native profile",
    ),
    "PM-VIEW-009": (
        "profile",
        ["V-CC-07", "V-CC-08"],
        "TS 및 trie의 state·transition·terminal count 표현",
    ),
    "PM-VIEW-010": (
        "profile",
        ["V-CC-09", "V-CC-10"],
        "지원 alignment 결과와 footprint 비교 matrix 표현",
    ),
    "PM-VIEW-011": ("profile", ["V-CC-11"], "Native SNA의 방향·weight·분모·근거 표현"),
    "PM-VIEW-012": (
        "partial",
        ["V-CC-15", "V-CC-16"],
        "Case-time dotted chart와 spectrum 지원; 일반 축/색/relative-time 설정 미완성",
    ),
    "PM-VIEW-013": ("partial", ["V-CC-17"], "분포 chart 지원; semilog-x 축 미지원"),
    "PM-VIEW-014": (
        "partial",
        ["V-CC-12", "V-OC-03", "V-OC-04", "V-OC-05"],
        "Object/type/attribute network 지원; 전체 양측 DFG interleaving overlay 미완성",
    ),
    "PM-VIEW-015": (
        "partial",
        ["V-CC-14", "V-CC-18"],
        "Decision tree와 variant duration 지원; normalized spacing/top-N 전체 미완성",
    ),
    "PM-VIEW-016": (
        "profile",
        ["V-CC-13"],
        "GraphPanel의 명시 ID·평행 간선·self-loop 표현. NetworkX drop-in API와 구분",
    ),
    "OC-VIEW-001": (
        "partial",
        ["V-OC-02"],
        "OCPN 및 제한된 성능 annotation; 참조 전체 지표·표기 동등성 미검증",
    ),
    "OC-VIEW-002": (
        "profile",
        ["V-OC-06"],
        "Native constraint graph·평가·unknown·근거 표현",
    ),
    "OC-VIEW-003": (
        "profile",
        ["V-OC-07"],
        "객체 instance/shared-event chevron, neutral 및 방향 선택. OCPA 근사 variant 정의로 변경하지 않음",
    ),
    "OC-VIEW-004": (
        "profile",
        ["V-OC-08"],
        "Native joint alignment의 move·binding·객체 lane 표현",
    ),
    "OC-REL-003": (
        "partial",
        [],
        "속성 이력/as-of 계산과 표는 존재하나 전용 객체 속성 시계열 표현의 완전한 대응 미확인",
    ),
}

EXCLUDED_NOTES = {
    "PM-IO-002": "XES reader는 있으나 공개 XES writer·gzip export·metadata 왕복 경로 미확인.",
    "PM-IO-011": "CSV bundle profile은 지원. Parquet API는 있으나 최종 환경의 pyarrow.lib 부재로 관련 14개 검사는 skip. 전체 행을 완료로 취급하지 않음.",
    "PM-IO-013": "OCEL 2 exporter는 있으나 OCEL 1/enriched/extended CSV/classic SQLite writer profile 미확인.",
    "PM-IO-014": "Compact CSV 및 CSV/Parquet bundle writer 미확인. Reader 존재는 exporter 구현 근거가 아님.",
    "PM-IO-015": "신규 PNML reader/writer: 명시 accepting marking을 가진 ordinary weighted P/T profile. 확장 arc·복수 final marking 미지원.",
    "PM-IO-016": "신규 PTML reader/writer: 명시 tree operator 및 binary/tau-exit loop profile.",
    "PM-IO-017": "Native result JSON과 별개인 upstream DFG 파일 형식 reader/writer 미확인.",
    "PM-IO-018": "신규 plain task/XOR/AND BPMN 교환. DI도 거부하므로 일반 편집기 파일 호환 행은 부분 지원 유지.",
    "PM-IO-019": "Unified reader는 로컬 파일/명시 record mapping 대상. URL 취득 adapter 미확인.",
    "PM-STREAM-002": "XES 내부 XML chunk parser의 yield는 존재하지만 공개 event/trace iterator·backpressure 계약은 미확인.",
    "OC-IO-005": "OCEL 2 exporter와 별개인 OCPA OCEL 1 JSON writer 미확인.",
    "PM-UTIL-008": "CaseLog 생성자로 검산 로그를 만들 수 있으나 활동 문자열 전용 parser 대응 API는 미확인.",
    "PM-UTIL-009": "PTML/JSON/ProcessTree 생성자는 지원하나 참조 process-tree 텍스트 문법 parser는 미확인.",
    "PM-UTIL-010": "POWL 모델/JSON은 지원하나 참조 부분순서 텍스트 문법 parser는 미확인.",
    "PM-UTIL-011": "Native model/result JSON 및 새 XML 메모리 입출력은 지원; 모든 참조 로그/모델 bytes 형식은 아님.",
}


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def summary(rows):
    counts = Counter(row["assessment"] for row in rows)
    count = len(rows)
    return {
        "denominator": count,
        "counts": {key: counts[key] for key in LABELS},
        "profile_percent": round(100 * counts["profile"] / count, 1),
        "profile_or_partial_percent": round(
            100 * (counts["profile"] + counts["partial"]) / count, 1
        ),
        "registered_reference_acceptance_count": sum(
            row["reference_replacement_verified"] for row in rows
        ),
    }


def grouped(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: summary(group) for name, group in sorted(groups.items())}


def link(path):
    return f"[{path}](../../../{path})"


def write(path, text):
    path.write_bytes(text.encode("utf-8"))


def main():
    scope, union, w4 = read(SCOPE), read(UNION), read(W4)
    source = {row["id"]: row for row in scope["rows"]}
    old = {row["source_id"]: row for row in union["rows"]}
    excluded = {row["source_id"] for row in union["excluded_rows"]}
    assert len(source) == len(scope["rows"]) == 334
    assert len(old) == 268 and len(excluded) == 66
    assert set(old).isdisjoint(excluded) and set(old) | excluded == set(source)
    assert set(PROMOTIONS) <= set(old)
    assert set(VIEWS) == {
        r["id"] for r in scope["rows"] if r["area"] == "visualization"
    }
    view_text = (ROOT / VIEW).read_text(encoding="utf-8")
    packets = defaultdict(list)
    for packet in w4["packets"]:
        for sid in packet["source_scope_ids"]:
            assert sid in source
            packets[sid].append(packet)
    all_rows = []
    for sid, original in source.items():
        row_packets = packets.get(sid, [])
        prior = old.get(sid)
        core = bool(prior)
        old_status = prior["status"] if prior else original["implementation"]
        status = {
            "native_profile": "profile",
            "implemented": "profile",
            "partial": "partial",
            "absent": "absent",
            "unimplemented": "absent",
            "external_runtime_unverified": "external_runtime_unverified",
        }[old_status]
        files = set(prior["actual"]["sources"] if prior else original["pix_sources"])
        tests = set(prior["actual"]["tests"] if prior else [])
        basis = (
            "union_classification_carried_forward"
            if prior
            else "scope_surface_rechecked"
        )
        reason = (
            "기존 native/partial 분류를 유지. 경로·테스트 존재와 최신 통합 보고서를 연결했으며 전체 참조 알고리즘을 새로 실행 대조하지 않음."
            if prior
            else "기존 입출력/보조 경로와 현재 공개 표면을 대조. 참조 모든 옵션의 동등성은 미확인."
        )
        for packet in row_packets:
            files.update(packet["code_files"])
            tests.update(packet["test_files"])
        if sid in PROMOTIONS:
            assert old_status == "partial" and row_packets
            status, reason, basis = "profile", PROMOTIONS[sid], "w4_gap_reassessment"
        if sid in VIEWS:
            status, families, reason = VIEWS[sid]
            assert all(f"| {family} |" in view_text for family in families)
            basis = "visualization_family_crosswalk"
            files.update(
                (
                    "src/pix/viewer/visualization.py",
                    "src/pix/viewer/visual_case_adapters.py",
                    "src/pix/viewer/visual_object_adapters.py",
                    "src/pix/viewer/visual_model_adapters.py",
                    "src/pix/viewer/visual_chevrons.py",
                )
            )
            tests.update(
                (
                    "tests/viewer/test_visual_case_adapters.py",
                    "tests/viewer/test_visual_object_adapters.py",
                    "tests/viewer/test_visual_model_adapters.py",
                    "tests/viewer/test_visual_chevrons.py",
                )
            )
        if sid in EXCLUDED_NOTES:
            reason = EXCLUDED_NOTES[sid]
        if sid in ("PM-IO-015", "PM-IO-016"):
            status, basis = "profile", "w4_model_exchange_reassessment"
        if sid in ("PM-IO-011", "PM-IO-018"):
            status = "partial"
        if original["area"] == "integration" and status == "absent":
            reason = "현재 공개 모듈/API·pyproject에서 이 외부 연결 기능의 대응 경로 미확인. Schumpeter 책임 후보라도 분모에서 제외하지 않음."
        if not core and status == "absent":
            files.update(
                (
                    "src/pix/io.py",
                    "src/pix/event_log/__init__.py",
                    "src/pix/ocel/export/__init__.py",
                    "src/pix/model_io/__init__.py",
                    "pyproject.toml",
                )
            )
        for path in files | tests:
            assert (ROOT / path).is_file(), (sid, path)
        all_rows.append(
            {
                "id": sid,
                "library": original["library"],
                "area": original["area"],
                "domain": prior["domain"]
                if prior
                else "outside_calculation_denominator",
                "question": original["question"],
                "in_calculation_denominator": core,
                "historical_status": old_status,
                "assessment": status,
                "assessment_basis": basis,
                "reason": reason,
                "reference_replacement_verified": bool(
                    prior["reference_replacement_verified"]
                    if prior
                    else original["replacement_verified"]
                ),
                "domain_review_status": "not_yet_reviewed",
                "w4_packets": [p["id"] for p in row_packets],
                "w4_remaining_limits": sorted(
                    {limit for p in row_packets for limit in p["remaining_limits"]}
                ),
                "historical_gaps_not_current_claims": prior["residual_variant_gaps"]
                if prior
                else [original["remaining"]],
                "code_or_inspected_surface_files": sorted(files),
                "test_files": sorted(tests),
            }
        )
    calculation = [row for row in all_rows if row["in_calculation_denominator"]]
    production = sorted(
        p
        for p in (ROOT / "src/pix").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    fingerprints = [
        (p.relative_to(ROOT).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in production
    ]
    result = {
        "schema_version": "1.0",
        "assessment_date": "2026-09-18",
        "analyzed_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "production_tree_sha256": hashlib.sha256(
            json.dumps(fingerprints, separators=(",", ":")).encode()
        ).hexdigest(),
        "source_documents_sha256": {
            path: sha(path) for path in (SCOPE, UNION, W4, VIEW, VALIDATION)
        },
        "assessment_policy_sha256": sha("tools/report_replacement_progress.py"),
        "counting_unit": "Equally counted SCOPE review rows; NOT distinct algorithms, effort, or measured fraction inside a partial row.",
        "classification_meaning": LABELS,
        "classification_is_review_judgment": True,
        "full_replacement_percent": None,
        "runtime_or_differential_tests_executed_by_this_script": False,
        "upstream_online_rechecked": {
            "date": "2026-09-18",
            "pm4py": "2.7.23.8",
            "ocpa": "1.3.4",
            "sources": [
                "https://pypi.org/project/pm4py/",
                "https://pypi.org/project/ocpa/",
            ],
        },
        "overall": summary(all_rows),
        "by_library": grouped(all_rows, "library"),
        "calculation": summary(calculation),
        "calculation_by_library": grouped(calculation, "library"),
        "calculation_by_domain": grouped(calculation, "domain"),
        "by_area": grouped(all_rows, "area"),
        "calculation_by_area": grouped(calculation, "area"),
        "baseline_calculation": {
            "statuses": dict(Counter(row["status"] for row in old.values())),
            "profile_percent": round(
                100
                * sum(r["status"] == "native_profile" for r in old.values())
                / len(old),
                1,
            ),
        },
        "w4_calculation_promotions": sorted(PROMOTIONS),
        "w4_distinct_source_rows": len(packets),
        "w4_added_or_extended_distinct_source_rows": len(
            {
                sid
                for p in w4["packets"]
                if p["delivery"] == "added_or_extended"
                for sid in p["source_scope_ids"]
            }
        ),
        "rows": all_rows,
    }
    assert sum(result["overall"]["counts"].values()) == 334
    assert sum(result["calculation"]["counts"].values()) == 268
    assert all(not row["reference_replacement_verified"] for row in all_rows)
    DEST.mkdir(parents=True, exist_ok=True)
    write(
        DEST / "assessment.json",
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    )
    lines = [
        "# 334개 비교 행별 현재 profile 평가",
        "",
        "기준: 2026-09-18, 코드 commit `" + result["analyzed_commit"] + "`.",
        "",
        "이 표의 ‘명시 profile 구현’은 해당 native 입력·계산·출력 경로의 존재를 뜻하며 참조 전체 대체 완료가 아니다.",
        "모든 행의 참조 대체 승인과 사용자 도메인 승인은 미확인이다. 과거 registry는 수정하지 않았다.",
        "이전 gap 문장은 현재 상태로 재사용하지 않고 JSON의 historical_gaps_not_current_claims에 분리 보존했다.",
        "[평가 본문](../2026-09-18_PIX_PM4PY_OCPA_COMPLETION_ASSESSMENT.md), [기계 판독 근거](assessment.json)",
        "",
    ]
    for library in ("pm4py", "ocpa"):
        lines.extend(
            [
                f"## {library}",
                "",
                "| ID | 영역 / 업무 질문 | 현재 평가 | 판단 근거 | 코드·검증 |",
                "|---|---|---|---|---|",
            ]
        )
        for row in all_rows:
            if row["library"] != library:
                continue
            refs = row["test_files"][:2] or row["code_or_inspected_surface_files"][:2]
            evidence = " · ".join(link(path) for path in refs)
            if row["w4_packets"]:
                evidence += " · " + link(W4)
            cells = [
                row["id"],
                row["area"] + " / " + row["question"],
                LABELS[row["assessment"]],
                row["reason"],
                evidence,
            ]
            lines.append(
                "| "
                + " | ".join(
                    cell.replace("|", "\\|").replace("\n", " ") for cell in cells
                )
                + " |"
            )
        lines.append("")
    write(DEST / "ROW_ASSESSMENT.md", "\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "overall",
                    "by_library",
                    "calculation",
                    "calculation_by_library",
                    "calculation_by_domain",
                    "by_area",
                    "w4_distinct_source_rows",
                    "w4_added_or_extended_distinct_source_rows",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
