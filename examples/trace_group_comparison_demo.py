"""Create a portable, interactive comparison using synthetic labelled cases."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pix.case_centric import compare_trace_groups
from pix.case_centric.trace_comparison import TraceComparisonSpec
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import write_result
from pix.viewer import build_visualization, export_html, write_visualization


def demo_log() -> CaseLog:
    origin = datetime(2026, 10, 1, tzinfo=timezone.utc)
    groups = (
        (
            "정상",
            (
                ("접수", "검사", "처리", "완료"),
                ("접수", "검사", "처리", "완료"),
                ("접수", "검사", "처리", "완료"),
                ("접수", "검사", "승인", "처리", "완료"),
            ),
        ),
        (
            "비정상 · 재작업",
            (
                ("접수", "검사", "재작업", "검사", "처리", "완료"),
                ("접수", "검사", "재작업", "검사", "처리", "완료"),
                ("접수", "검사", "보류", "처리", "완료"),
            ),
        ),
        (
            "그룹 C · 검사 생략",
            (
                ("접수", "처리", "완료"),
                ("접수", "처리", "완료"),
                ("접수", "검사", "처리", "완료"),
            ),
        ),
    )
    traces = []
    for gi, (label, words) in enumerate(groups):
        for ci, word in enumerate(words):
            case_id = f"G{gi + 1}-{ci + 1:02}"
            traces.append(
                CaseTrace(
                    case_id,
                    tuple(
                        CaseEvent(
                            f"{case_id}/e{i}",
                            (
                                CaseAttribute("concept:name", "string", activity),
                                CaseAttribute(
                                    "time:timestamp",
                                    "date",
                                    origin + timedelta(days=gi, hours=ci, minutes=i),
                                ),
                            ),
                        )
                        for i, activity in enumerate(word)
                    ),
                    (CaseAttribute("quality_group", "string", label),),
                )
            )
    # A missing label is explicitly counted as unassigned, never made normal.
    traces.append(
        CaseTrace(
            "unlabelled",
            (
                CaseEvent(
                    "unlabelled/e0",
                    (
                        CaseAttribute("concept:name", "string", "접수"),
                        CaseAttribute("time:timestamp", "date", origin),
                    ),
                ),
            ),
        )
    )
    return CaseLog(tuple(traces))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".artifacts/trace-group-comparison")
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = compare_trace_groups(
        demo_log(),
        group_attribute="quality_group",
        spec=TraceComparisonSpec(reference_group="정상"),
    )
    document = build_visualization(result, title="그룹별 대표 Trace 비교 · 합성 데이터")
    export_html(
        document,
        args.output / "comparison.html",
        overwrite=args.overwrite,
        layout_engine="native",
    )
    write_result(
        result, args.output / "comparison.result.json", overwrite=args.overwrite
    )
    write_visualization(
        document,
        args.output / "comparison.visualization.json",
        overwrite=args.overwrite,
    )
    print(args.output / "comparison.html")


if __name__ == "__main__":
    main()
