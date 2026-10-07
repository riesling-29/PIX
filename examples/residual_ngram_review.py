"""Generate a reproducible Korean n-gram review from actual PIX results.

Run: python examples/residual_ngram_review.py --output <directory>
Synthetic inputs are explicitly marked. No LLM, browser, or external data
acquisition is involved in the calculations.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from pix.case_centric.context_ngrams import (
    ContextNGramSpec,
    fit_context_ngrams,
    transform_context_ngrams,
)
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, write_xes
from pix.results import result_json_bytes


def build_samples():
    sequences = (
        ("agent-search", ("검색", "열기", "검색", "열기", "저장")),
        ("agent-short", ("검색", "저장")),
        ("business", ("접수", "검토", "반려", "검토", "승인")),
        ("empty", ()),
    )
    data = CaseLog(
        tuple(
            CaseTrace(
                name,
                tuple(
                    CaseEvent(
                        f"{name}:{i}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for i, activity in enumerate(seq)
                ),
            )
            for name, seq in sequences
        )
    )
    results = {}
    for encoding in ("count", "binary", "tfidf"):
        fit = fit_context_ngrams(data, ContextNGramSpec(encoding=encoding))
        if fit.value is None:
            raise RuntimeError(fit.issues)
        results[encoding] = transform_context_ngrams(data, fit.value)
    # Identical source events considered separately versus an erroneous merge.
    boundary = CaseLog(
        (
            CaseTrace(
                "object-a",
                (CaseEvent("a", (CaseAttribute("concept:name", "string", "검색"),)),),
            ),
            CaseTrace(
                "object-b",
                (CaseEvent("b", (CaseAttribute("concept:name", "string", "저장"),)),),
            ),
        )
    )
    incorrect = CaseLog(
        (
            CaseTrace(
                "WRONG-global-order",
                tuple(e for t in boundary.traces for e in t.events),
            ),
        )
    )
    for name, log in (
        ("separate-objects", boundary),
        ("wrong-global-order", incorrect),
    ):
        fitted = fit_context_ngrams(log, ContextNGramSpec(ngram_min=2, ngram_max=2))
        results[name] = transform_context_ngrams(log, fitted.value)
    return data, results


def write_review(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    data, results = build_samples()
    write_xes(data, directory / "synthetic-input.xes", overwrite=True)
    for name, result in results.items():
        (directory / (name + ".json")).write_bytes(result_json_bytes(result))
    counted = results["count"].value.matrix
    binary = results["binary"].value.matrix
    weighted = results["tfidf"].value.matrix
    sections = [
        "<h1>PIX n-gram 계산 샘플</h1>",
        "<p>합성 예제 · 실제 PIX 계산 출력 · 각 case가 문서 하나입니다. 빈 case도 IDF의 문서 수에 포함합니다.</p>",
    ]
    for index, trace in enumerate(data.traces):
        sections.append(
            f"<h2>{html.escape(trace.id)}</h2><p class='sequence'>{html.escape(' → '.join(e.activity for e in trace.events) or '(빈 실행)')}</p>"
        )
        rows = []
        for j, column in enumerate(counted.columns):
            if not counted.rows[index].values[j]:
                continue
            rows.append(
                f"<tr><td>{len(column.terms)}</td><td>{html.escape(' → '.join(column.terms))}</td><td>{counted.rows[index].values[j]:g}</td><td>{binary.rows[index].values[j]:g}</td><td>{weighted.rows[index].values[j]:.4f}</td></tr>"
            )
        sections.append(
            "<table><thead><tr><th>n</th><th>연속 묶음</th><th>Count</th><th>Binary</th><th>TF-IDF</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
    sections.append(
        "<h2>객체 경계를 합치면 생기는 허위 패턴</h2><p>객체 A는 검색만, 객체 B는 저장만 수행했습니다.</p>"
    )
    for name in ("separate-objects", "wrong-global-order"):
        value = results[name].value
        terms = [" → ".join(c.terms) for c in value.matrix.columns]
        sections.append(
            f"<p><strong>{html.escape(name)}</strong>: {html.escape(', '.join(terms) or '2-gram 없음')}</p>"
        )
    sections.append(
        "<p>TF-IDF = 횟수 × [log((1+문서 수)/(1+해당 묶음이 있는 문서 수))+1]. 이 샘플은 L2 정규화를 사용하지 않습니다. 높은 값이 성공률이나 최적성을 의미하지 않습니다.</p>"
    )
    content = (
        "<!doctype html><html lang='ko'><meta charset='utf-8'><title>PIX n-gram review</title><style>body{font:16px/1.7 system-ui,sans-serif;color:#25282c;background:#f4f5f6;max-width:1050px;margin:40px auto;padding:24px}h1{font-size:30px}h2{margin-top:40px}table{width:100%;border-collapse:collapse;background:white}td,th{padding:9px 16px;border-bottom:1px solid #ddd;text-align:left}th{background:#e9ebee}.sequence{padding:16px;background:#fff;border-left:3px solid #555}</style>"
        + "".join(sections)
        + "</html>"
    )
    (directory / "ngram-review.html").write_text(content, encoding="utf-8")
    summary = {
        name: {
            "status": result.status.value,
            "occurrences": result.value.occurrence_count,
            "columns": len(result.value.matrix.columns),
        }
        for name, result in results.items()
    }
    (directory / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(write_review(parser.parse_args().output), ensure_ascii=True))
