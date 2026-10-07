"""Create a hand-checkable discovery, joint execution and evaluation report.

This synthetic example requires no external process-mining library or server.
Run: python examples/model_evaluation.py --output .artifacts/v040/demo
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from native_pipeline import demo_log

from pix._publication import publish_bytes
from pix.api import (
    ConstraintSpec,
    CountRule,
    DiscoverySpec,
    ModelArtifact,
    ObjectAlignmentSpec,
    ObjectContextSpec,
    OCDFGSpec,
    OCPNDiscoverySpec,
    PrecedenceRule,
    PrefixPrecisionSpec,
    ResponseRule,
    TimedResponseRule,
    TraceSpec,
    align_object_log,
    discover_ocdfg,
    discover_ocpn,
    discover_process_tree,
    evaluate_constraints,
    export_ocel,
    measure_object_context,
    measure_prefix_precision,
    process_tree_to_petri_net,
    reconstruct_traces,
    write_model,
    write_result,
)
from pix.ocel import canonical_digest
from pix.viewer import build_graph, build_model_graph, export_html


def ratio(value: tuple[int, int] | None) -> str:
    return "알 수 없음" if value is None else f"{value[0]} / {value[1]}"


def require_computed(result) -> None:
    if result.status.value != "computed":
        raise RuntimeError(
            f"{result.operator_id}: {result.status.value}; {result.issues}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".artifacts/v040/demo"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    log = demo_log()
    for kind in ("json", "xml", "sqlite"):
        export_ocel(
            log, args.output / f"ocel.{kind}", format=kind, overwrite=args.overwrite
        )

    traces = reconstruct_traces(log, TraceSpec("Order"))
    tree = discover_process_tree(traces, DiscoverySpec(algorithm="pix.im.v1"))
    require_computed(tree)
    net = process_tree_to_petri_net(tree.value)
    ocpn = discover_ocpn(
        log,
        OCPNDiscoverySpec(
            ("Order", "Package"),
            "observed_range",
            "unique_activity",
            classic_algorithm="pix.im.v1",
        ),
    )
    require_computed(ocpn)
    joint = align_object_log(
        log, ocpn.value.model, ObjectAlignmentSpec(("Order", "Package"))
    )
    context = measure_object_context(
        log, ocpn.value.model, ObjectContextSpec(("Order", "Package"))
    )
    require_computed(joint)
    require_computed(context)
    ocdfg = discover_ocdfg(log, OCDFGSpec(("Order", "Package")))
    include = measure_prefix_precision(traces, net, PrefixPrecisionSpec("include"))
    exclude = measure_prefix_precision(traces, net, PrefixPrecisionSpec("exclude"))
    closed = evaluate_constraints(
        traces,
        ConstraintSpec(
            (
                CountRule("주문당-접수-한번", "주문 접수", 1, 1),
                ResponseRule("접수-후-배송", "주문 접수", "배송"),
                PrecedenceRule("배송-전-접수", "주문 접수", "배송"),
                TimedResponseRule(
                    "9분-이내-배송", "주문 접수", "배송", 0, 540_000_000, "any"
                ),
            ),
            "closed",
        ),
    )
    open_rules = evaluate_constraints(
        traces,
        ConstraintSpec((ResponseRule("배송-후-보관", "배송", "보관"),), "open"),
    )
    results = {
        "traces": traces,
        "process-tree": tree,
        "ocdfg": ocdfg,
        "ocpn-discovery": ocpn,
        "joint-alignment": joint,
        "prefix-include-end": include,
        "prefix-exclude-end": exclude,
        "object-context": context,
        "closed-rules": closed,
        "open-rules": open_rules,
    }
    for name, result in results.items():
        write_result(result, args.output / f"{name}.json", overwrite=args.overwrite)
    for name, model, source in (
        ("classical-model", net, tree),
        ("discovered-ocpn", ocpn.value.model, ocpn),
    ):
        artifact = ModelArtifact(model, "discovered", source.computation_id)
        write_model(artifact, args.output / f"{name}.json", overwrite=args.overwrite)
        export_html(
            build_model_graph(artifact),
            args.output / f"{name}.html",
            overwrite=args.overwrite,
        )
    export_html(
        build_graph(ocdfg), args.output / "ocdfg.html", overwrite=args.overwrite
    )

    lines = [
        "# PIX 0.4.0 합성 주문 로그 실행 결과",
        "",
        "이 문서의 값은 아래 입력을 PIX 자체 계산에 실제 전달한 결과다.",
        "[관측 OCDFG](ocdfg.html) · [발견 Petri net](classical-model.html) · [발견 OCPN](discovered-ocpn.html)",
        "",
        "## 원본 입력",
        "",
        "| Event | 시각 (UTC) | 활동 | 참여 객체 |",
        "|---|---|---|---|",
    ]
    for event in log.events:
        objects = sorted({rel.object for rel in log.e2o if rel.event == event.id})
        lines.append(
            f"| {event.id} | {event.time:%H:%M} | {event.type} | {', '.join(objects)} |"
        )
    lines.extend(
        [
            "",
            "## 발견 OCPN의 관측 참여 분포",
            "",
            "각 구간은 선택한 observed_range 정책이다. 관측되지 않은 중간 수와 객체형별 조합도 허용할 수 있다.",
            "관측 로그의 수락 경로를 확인했지만 공동 soundness나 업무 규범을 인증하지 않는다.",
            "",
            "| 활동 | 객체형 | 참여 수: event 수 | Arc | 최소~최대 |",
            "|---|---|---|---|---|",
        ]
    )
    for profile in ocpn.value.cardinality_profiles:
        histogram = ", ".join(
            f"{count}: {frequency}" for count, frequency in profile.histogram
        )
        lines.append(
            f"| {profile.activity} | {profile.object_type} | {histogram} | {profile.arc_kind} | {profile.min_objects}~{profile.max_objects} |"
        )
    lines.extend(
        [
            "",
            "## 공동 alignment의 실제 단계",
            "",
            f"상태: {joint.value.status}; 최소 비용: {joint.value.cost}; 비용 단위: {joint.value.cost_unit}.",
            "공유 event는 한 번만 소비한다. 아래 순서는 가능한 최적 경로 하나이며 독립 event의 유일한 순서가 아니다.",
            "",
            "| 단계 | 이동 | Event | 활동 | 실제 참여 객체 | 비용 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for index, move in enumerate(joint.value.moves, 1):
        participants = "; ".join(
            f"{kind}: {', '.join(objects)}" for kind, objects in move.objects
        )
        lines.append(
            f"| {index} | {move.kind} | {move.event_id or '—'} | {move.activity or 'silent'} | {participants or '없음'} | {move.cost} |"
        )
    lines.extend(
        [
            "",
            "전후 marking과 transition ID는 `joint-alignment.json`에 모두 보존된다.",
            "",
            "## 평가 값과 모집단",
            "",
            "| 계산 | 분자 / 분모 | 범위 |",
            "|---|---|---|",
            f"| Prefix precision, 종료 포함 | {ratio(include.value.whole_log_ratio)} | 객체 Trace, prefix 발생 가중 |",
            f"| Prefix precision, 종료 제외 | {ratio(exclude.value.whole_log_ratio)} | 후속 event가 있는 prefix 발생 가중 |",
            f"| Object-context fitness | {ratio(context.value.full_scope_fitness_ratio)} | 구체 객체 이력, activity+참여 객체 행동 집합 |",
            f"| Object-context precision | {ratio(context.value.full_scope_precision_ratio)} | 같은 범위의 micro 집계, 종료 제외 |",
            "",
            "이 값들을 서로 같은 지표로 합치거나 PM4Py/OCPA의 동명 값과 동일하다고 가정하지 않는다.",
            "",
            "## 규칙별 판단",
            "",
            "| 관측 정책 | 규칙 | 충족 | 위반 | 대기 | 충족/활성화 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for result in (closed, open_rules):
        for rule in result.value.rules:
            lines.append(
                f"| {result.spec.observation_policy} | {rule.rule_id} | {rule.fulfilled_count} | {rule.violated_count} | {rule.pending_count} | {ratio(rule.fulfillment_ratio)} |"
            )
    lines.extend(
        [
            "",
            "9분 이내 배송은 O2만 충족하고 O1·O3은 위반한다. 열린 관측창의 배송 후 보관은 3건 모두 대기다.",
            "",
            "## 적용 범위",
            "",
            "2026-09-10의 합성 입력과 명시한 PIX profile에 한정한 결과다. 입력·정의·코드가 바뀌면 재계산한다.",
            "독립 반례가 계산 규칙이나 coverage와 충돌하면 해당 판단을 철회한다. 대용량 성능과 외부 라이브러리 대비 우위는 알 수 없음이다.",
            "",
        ]
    )
    publish_bytes(
        "\n".join(lines).encode("utf-8"),
        args.output / "review.md",
        overwrite=args.overwrite,
    )
    manifest = {
        "source_digest": canonical_digest(log).identifier,
        "results": {
            name: {
                "status": result.status.value,
                "computation_id": result.computation_id,
            }
            for name, result in results.items()
        },
        "review": "review.md",
        "joint_cost": joint.value.cost,
    }
    publish_bytes(
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        args.output / "manifest.json",
        overwrite=args.overwrite,
    )
    print(f"Report: {args.output / 'review.md'}")


if __name__ == "__main__":
    main()
