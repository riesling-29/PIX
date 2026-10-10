"""Create an offline catalog from two explicitly synthetic case groups."""

import argparse
from pathlib import Path

from pix.case_centric import catalog_trace_variants
from pix.case_centric.trace_catalog import TraceCatalogSpec
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import write_result
from pix.viewer import build_visualization, export_html, write_visualization


def demo_log():
    words = (
        ("접수", "검사", "처리", "완료"),
        ("접수", "검사", "승인", "처리", "완료"),
        ("접수", "처리", "완료"),
        ("접수", "검사", "재작업", "검사", "완료"),
        ("접수", "검사", "보류"),
    )
    traces = []
    for gi, (group, counts) in enumerate(
        (("정상", (60, 20, 10, 5, 5)), ("비정상 · 재작업", (2, 1, 3, 9, 5)))
    ):
        for vi, (word, count) in enumerate(zip(words, counts)):
            for ci in range(count):
                cid = f"G{gi}/V{vi}/C{ci:03}"
                traces.append(
                    CaseTrace(
                        cid,
                        tuple(
                            CaseEvent(
                                f"{cid}/E{ei}",
                                (CaseAttribute("concept:name", "string", a),),
                            )
                            for ei, a in enumerate(word)
                        ),
                        (CaseAttribute("quality_group", "string", group),),
                    )
                )
    traces.append(CaseTrace("unlabelled", ()))
    return CaseLog(tuple(traces))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".artifacts/trace-variant-catalog")
    )
    parser.add_argument("--top-variant-percent", type=int, default=20)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = catalog_trace_variants(
        demo_log(),
        group_attribute="quality_group",
        spec=TraceCatalogSpec(top_variant_percent=args.top_variant_percent),
    )
    view = build_visualization(result, title="Trace 빈도와 복수 선택 · 합성 데이터")
    export_html(
        view,
        args.output / "catalog.html",
        layout_engine="native",
        overwrite=args.overwrite,
    )
    write_result(result, args.output / "catalog.result.json", overwrite=args.overwrite)
    write_visualization(view, args.output / "catalog.json", overwrite=args.overwrite)
    print(args.output / "catalog.html")


if __name__ == "__main__":
    main()
