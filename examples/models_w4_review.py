"""Reproducible, hand-checkable MODEL/W4 domain review cases.

Run from an installed PIX environment::

    python examples/models_w4_review.py --output-directory .artifacts/models-w4-review

The fixtures are deliberately small. They exercise native contracts, not
PM4Py/OCPA equivalence or production-scale performance. No test fixture is
imported, and no external dataset, library, service, or random global is needed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pix.case_centric import feature_dataset as fd
from pix.case_centric import resource_simulation as rs
from pix.case_centric.advanced import BoseDriftSpec, detect_bose_drift
from pix.case_centric.coverability import CoverabilitySpec, coverability
from pix.case_centric.decision_evaluation import (
    DecisionEvaluationRow,
    DecisionEvaluationSpec,
    EvaluationFeature,
    evaluate_decision_tree,
)
from pix.case_centric.discovery import discover_prefix_tree
from pix.case_centric.drift_evaluation import adjust_drift_pvalues
from pix.case_centric.extended_nets import (
    InhibitorArc,
    ResetArc,
    ResetInhibitorNet,
    StochasticPetriNet,
    StochasticTransition,
    fire_reset_inhibitor,
    reset_inhibitor_is_enabled,
    sample_stochastic_step,
    stochastic_transition_probabilities,
)
from pix.case_centric.features import FeatureSpec
from pix.case_centric.inductive import discover_inductive_strict
from pix.case_centric.lifecycle import pair_lifecycle_events
from pix.case_centric.maximal_decomposition import (
    maximal_decompose_model,
    recompose_maximal_decomposition,
)
from pix.case_centric.model_labels import (
    ModelLabelRenameSpec,
    activity_labels,
    rename_activity_labels,
)
from pix.case_centric.powl import POWLNode
from pix.case_centric.powl_conversion import powl_to_process_tree
from pix.case_centric.revisable_stream import (
    RetainedCaseEvent,
    RevisableCaseStream,
    RevisableCaseStreamSpec,
)
from pix.case_centric.simulation import CaseArrival, DurationDistribution, FIFOInput
from pix.case_centric.split_miner import SplitBPMN, SplitBPMNFlow, SplitBPMNNode
from pix.case_centric.timed_playout import TimedPlayoutSpec, playout_timed_petri_net
from pix.case_centric.tree_bordered import tree_to_transition_bordered_petri_net
from pix.case_centric.trie_conversion import trie_to_petri_net
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputationResult
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.model_io import (
    dumps_bpmn,
    dumps_pnml,
    dumps_ptml,
    loads_bpmn,
    loads_pnml,
    loads_ptml,
)
from pix.object_centric.action_planning import (
    ActionMatchEnumerationSpec,
    ActionPlanningSpec,
    enumerate_action_matches,
    plan_actions,
)
from pix.object_centric.actions import (
    ActionCandidate,
    ActionPattern,
    ConstraintInterval,
)
from pix.object_centric.conformance import ObjectReplaySpec
from pix.object_centric.features import (
    ObjectFeature,
    ObjectFeatureFitSpec,
    ObjectFeatureSpec,
    extract_object_features,
    fit_object_feature_encoder,
    transform_object_features,
)
from pix.object_centric.learning import (
    ObjectKStepSpec,
    ObjectRegressionFitSpec,
    ObjectRegressionPredictSpec,
    build_object_k_step_dataset,
    evaluate_object_regression,
    fit_object_regression,
    inverse_transform_object_features,
    predict_object_regression,
)
from pix.object_centric.operational_impact import (
    OperationalImpactSpec,
    assess_operational_impact,
)
from pix.object_centric.revisable_stream import OCRevisableStream, OCSourceOffset
from pix.object_centric.subprocess import (
    ObjectSubprocessPipelineSpec,
    ObjectTypedSubprocessSpec,
    local_ocpn_subprocess,
    transform_ocpn_subprocess,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.ocel.model import Attribute, EventAttr, ValueType
from pix.results import result_json_bytes

ORIGIN = datetime(2026, 9, 17, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ReviewNote:
    question: str
    inputs: str
    expected: str
    scope: str


def at(seconds: int) -> datetime:
    return ORIGIN + timedelta(seconds=seconds)


def _case_log(*words: str) -> CaseLog:
    return CaseLog(
        tuple(
            CaseTrace(
                f"case-{i}",
                tuple(
                    CaseEvent(
                        f"event-{i}-{j}",
                        (
                            CaseAttribute("concept:name", "string", label),
                            CaseAttribute("time:timestamp", "date", at(j * 5)),
                        ),
                    )
                    for j, label in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def _sequence_net() -> PetriNet:
    return PetriNet(
        tuple(Place(p) for p in ("p", "q", "r")),
        (Transition("a", "A"), Transition("b", "B")),
        tuple(Arc(*pair) for pair in (("p", "a"), ("a", "q"), ("q", "b"), ("b", "r"))),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )


def _object_net() -> ObjectCentricPetriNet:
    return ObjectCentricPetriNet(
        tuple(TypedPlace(p, "Item") for p in ("p", "q", "r")),
        (Transition("a", "A"), Transition("b", "B")),
        tuple(
            ObjectArc(start, end, True, 1, 2)
            for start, end in (("p", "a"), ("a", "q"), ("q", "b"), ("b", "r"))
        ),
        ObjectMarking((ObjectToken("p", "i1"), ObjectToken("p", "i2"))),
        ObjectMarking((ObjectToken("r", "i1"), ObjectToken("r", "i2"))),
        (("i1", "Item"), ("i2", "Item")),
    )


def _object_log() -> OCEL:
    return OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("Item"),),
        events=(Event("e0", "A", at(0)), Event("e1", "B", at(1))),
        objects=(Object("i1", "Item"), Object("i2", "Item")),
        e2o=tuple(E2O(e, o, "flow") for e in ("e0", "e1") for o in ("i1", "i2")),
    )


def _learning_cases() -> dict[str, ComputationResult]:
    # Each order has its own object and execution. The next observed numeric
    # amount is exactly 2*x+1, and the held-out order is absent from training.
    events, objects, links = [], [], []
    for i in range(5):
        objects.append(Object(f"order-{i}", "Order"))
        for step, amount in enumerate((i, 2 * i + 1)):
            identity = f"order-{i}-event-{step}"
            events.append(
                Event(identity, "Observe", at(step), (EventAttr("amount", amount),))
            )
            links.append(E2O(identity, f"order-{i}", "flow"))
    log = OCEL(
        event_types=(EventType("Observe", (Attribute("amount", ValueType.INTEGER),)),),
        object_types=(ObjectType("Order"),),
        events=tuple(events),
        objects=tuple(objects),
        e2o=tuple(links),
    )
    features = extract_object_features(
        log,
        ObjectFeatureSpec((ObjectFeature("characteristic_value", attribute="amount"),)),
    )
    dataset = build_object_k_step_dataset(features, ObjectKStepSpec(1, (0,), (0,)))
    ordered = sorted(
        dataset.value.samples, key=lambda sample: sample.inputs[0].values[0]
    )
    model = fit_object_regression(
        dataset, ObjectRegressionFitSpec(tuple(s.sample_id for s in ordered[:4]))
    )
    predictions = predict_object_regression(
        dataset, model, ObjectRegressionPredictSpec((ordered[4].sample_id,))
    )
    # Fit inverse statistics on rows belonging only to the four training orders.
    heldout_rows = {
        r.row_id for r in features.value.rows if "order-4" in r.object_members
    }
    train_rows = tuple(
        r.row_id for r in features.value.rows if r.row_id not in heldout_rows
    )
    encoder = fit_object_feature_encoder(features, ObjectFeatureFitSpec(train_rows))
    inverse = inverse_transform_object_features(
        transform_object_features(features, encoder), encoder
    )
    return {
        "object_k_step": dataset,
        "object_feature_inverse": inverse,
        "object_regression_fit": model,
        "object_regression_predict": predictions,
        "object_regression_evaluation": evaluate_object_regression(
            predictions, dataset
        ),
    }


def build_review_cases() -> dict[str, ComputationResult]:
    """Return actual native results; names match :func:`review_notes` exactly."""
    results: dict[str, ComputationResult] = {}
    net = _sequence_net()
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    results["coverability"] = coverability(
        net, CoverabilitySpec(target=Marking((("r", 1),)))
    )
    results["powl_to_tree"] = powl_to_process_tree(
        POWLNode(
            "partial_order",
            children=(POWLNode("activity", "A"), POWLNode("activity", "B")),
        )
    )
    results["transition_bordered"] = tree_to_transition_bordered_petri_net(tree)
    results["trie_to_net"] = trie_to_petri_net(
        discover_prefix_tree(_case_log("A", "AB")).value
    )
    labels = activity_labels(net)
    results["activity_labels"] = labels
    occurrence = next(
        item.occurrence_id for item in labels.value.occurrences if item.node_id == "a"
    )
    results["rename_labels"] = rename_activity_labels(
        net, ModelLabelRenameSpec(((occurrence, "Approve"),))
    )
    decomposition = maximal_decompose_model(net)
    results["maximal_decomposition"] = decomposition
    results["maximal_recomposition"] = recompose_maximal_decomposition(decomposition)
    results["strict_inductive"] = discover_inductive_strict(_case_log("ABC", "A"))

    log = _case_log("ABC", "AB")
    observation = fd.ObservationSpec(at(5))
    results["observation_dataset"] = fd.observation_dataset(
        log,
        observation,
        follow_up=(
            fd.CaseFollowUp("case-0", at(12), at(12)),
            fd.CaseFollowUp("case-1", at(12)),
        ),
    )
    results["leakage_split"] = fd.leakage_safe_split(
        _case_log("A", "A", "A", "A"),
        fd.LeakageSplitSpec(
            train_fraction=0.5,
            shared_case_groups=(("case-0", "case-1"), ("case-1", "case-2")),
        ),
    )
    encoded = fd.fit_observation_encoder(
        log,
        fd.ObservationEncoderSpec(observation, FeatureSpec(level="event")),
        training_case_ids=("case-0",),
    )
    results["observation_encoder"] = encoded
    results["observation_matrix"] = fd.transform_observations(log, encoded.value)
    results["case_sequence_tensor"] = fd.encode_case_sequences(
        log, encoded.value, fd.CaseSequenceSpec(3)
    )
    results["decision_evaluation"] = evaluate_decision_tree(
        CaseLog(tuple(CaseTrace(c) for c in ("train-low", "train-high", "held-out"))),
        (
            DecisionEvaluationRow("low", "train-low", (0,), "no"),
            DecisionEvaluationRow("high", "train-high", (10,), "yes"),
            DecisionEvaluationRow("held", "held-out", (10,), "yes"),
        ),
        DecisionEvaluationSpec(
            (EvaluationFeature("amount", "numeric"),),
            ("train-low", "train-high"),
            ("held-out",),
        ),
    )
    results["drift_adjustment"] = adjust_drift_pvalues(
        detect_bose_drift(
            _case_log("A", "A", "A"), BoseDriftSpec(sublog_size=1, window_size=1)
        )
    )

    jobs = FIFOInput((CaseArrival("job-1", 0, ("A",)), CaseArrival("job-2", 0, ("A",))))
    single = rs.ResourceSimulationSpec(
        (("A", (("R", 1),)),),
        (rs.ResourcePool("R", 1),),
        (("A", DurationDistribution("fixed", 2)),),
    )
    double = replace(single, resource_pools=(rs.ResourcePool("R", 2),))
    results["resource_simulation"] = rs.simulate_resources(jobs, single)
    results["resource_comparison"] = rs.compare_resource_scenarios(
        jobs, rs.ResourceComparisonSpec((("single", single), ("double", double)))
    )
    lifecycle = CaseLog(
        tuple(
            CaseTrace(
                f"service-{duration}",
                tuple(
                    CaseEvent(
                        f"service-{duration}-{phase}",
                        (
                            CaseAttribute("concept:name", "string", "A"),
                            CaseAttribute("lifecycle:transition", "string", phase),
                            CaseAttribute("time:timestamp", "date", at(offset)),
                        ),
                    )
                    for phase, offset in (("start", 0), ("complete", duration))
                ),
            )
            for duration in (2, 4)
        )
    )
    results["resource_duration_fit"] = rs.fit_resource_durations(
        pair_lifecycle_events(lifecycle), rs.ResourceDurationFitSpec("exponential")
    )
    results["timed_playout"] = playout_timed_petri_net(
        StochasticPetriNet(
            net,
            (
                StochasticTransition("a", 1, DurationDistribution("fixed", 2)),
                StochasticTransition("b", 1, DurationDistribution("fixed", 3)),
            ),
        ),
        TimedPlayoutSpec(samples=1),
    )

    stream = RevisableCaseStream(RevisableCaseStreamSpec("domain-review"))
    for label, second in (("A", 1), ("C", 3)):
        stream.upsert_event(
            RetainedCaseEvent("case", label, label, at(second), second),
            operation_id=label,
        )
    stream.snapshot()
    stream.upsert_event(
        RetainedCaseEvent("case", "B", "B", at(2), 2), operation_id="late-B"
    )
    results["case_stream_revision"] = stream.snapshot()

    initial = OCEL(
        event_types=(EventType("A"), EventType("Bridge")),
        object_types=(ObjectType("Item"),),
        events=(Event("left", "A", at(0)), Event("right", "A", at(2))),
        objects=(Object("i1", "Item"), Object("i2", "Item")),
        e2o=(E2O("left", "i1", "flow"), E2O("right", "i2", "flow")),
    )
    oc_stream = OCRevisableStream(initial)
    oc_stream.snapshot()
    oc_stream.upsert_event(
        Event("bridge", "Bridge", at(1)),
        (E2O("bridge", "i1", "flow"), E2O("bridge", "i2", "flow")),
        operation_id="bridge",
        source_offset=OCSourceOffset("demo", 1),
    )
    results["object_stream_revision"] = oc_stream.snapshot()
    results["action_plan"] = plan_actions(
        (ActionCandidate("A", 2), ActionCandidate("B", 1)),
        ActionPlanningSpec(
            ORIGIN, 20, ("A", "B"), precedence=(("A", "B"),), objective="min_makespan"
        ),
    )
    results["action_matches"] = enumerate_action_matches(
        (ConstraintInterval("fault-1", "fault", at(0), at(1), ("i1",)),),
        ActionMatchEnumerationSpec(
            (ActionPattern("repair-rule", "repair", 2, (("f", "fault"),)),)
        ),
    )
    results["operational_impact"] = assess_operational_impact(
        _object_log(),
        _object_net(),
        OperationalImpactSpec(ObjectReplaySpec(("Item",)), ("a",), 0, 1),
    )
    boundary = ObjectTypedSubprocessSpec("Item", "p", "q")
    results["object_subprocess"] = local_ocpn_subprocess(_object_net(), boundary)
    results["object_subprocess_pipeline"] = transform_ocpn_subprocess(
        _object_net(), ObjectSubprocessPipelineSpec(boundary)
    )
    results.update(_learning_cases())
    return results


def review_notes() -> dict[str, ReviewNote]:
    """Domain questions and independent expected values, before computation."""
    return {
        "strict_inductive": ReviewNote(
            "함께 생략되는 활동 구간을 보존하는가?",
            "관측 case ABC, A",
            "가시 언어 {A,ABC}; AB와 AC는 허용하지 않음",
            "선택적 구간에 대한 strict sequence profile. 모든 미관측 행동을 배제한다는 일반적 보장은 아님.",
        ),
        "coverability": ReviewNote(
            "종료 토큰에 도달 가능한가?",
            "p→A→q→B→r, 초기 p=1",
            "bounded=True, target_coverable=True, 각 place 최대 1",
            "일반 weighted P/T net. Coverability와 정확한 도달성을 일반적으로 동일시하지 않는다.",
        ),
        "powl_to_tree": ReviewNote(
            "순서 제약이 없는 A/B를 변환하면?",
            "두 독립 활동을 가진 POWL partial order",
            "parallel(A,B): AB와 BA",
            "series-parallel로 표현 가능한 부분순서만 변환.",
        ),
        "transition_bordered": ReviewNote(
            "트리의 활동 순서를 보존하는가?",
            "sequence(A,B)",
            "허용 가시 언어 {AB}",
            "silent 경계 transition은 이벤트가 아니다.",
        ),
        "trie_to_net": ReviewNote(
            "중간 prefix의 종료 선택을 보존하는가?",
            "관측 case A, AB",
            "허용 언어 {A,AB}; B 단독은 불가",
            "유한 prefix trie 언어만 보존; 미관측 일반화 아님.",
        ),
        "activity_labels": ReviewNote(
            "라벨과 occurrence ID를 분리하는가?",
            "transition a:A, b:B",
            "서로 다른 occurrence 2개, 라벨 A/B",
            "라벨은 실행 정체성이 아니다.",
        ),
        "rename_labels": ReviewNote(
            "정확히 하나의 발생 위치만 바꾸는가?",
            "a의 라벨 A→Approve",
            "a:Approve, b:B, 원본 a:A 유지",
            "라벨 치환은 관측 언어 이름을 변경한다.",
        ),
        "maximal_decomposition": ReviewNote(
            "연결된 net도 경계 transition을 공유하며 나누는가?",
            "p→A→q→B→r, 라벨 모두 유일",
            "component3개; A/B는 인접 component의 공유 경계",
            "동일 라벨·silent transition은 독립적으로 쪼개지 않는다.",
        ),
        "maximal_recomposition": ReviewNote(
            "분해 후 원래 구조와 marking을 복원하는가?",
            "위 분해 결과",
            "원본 Petri net과 정확히 동일",
            "재조합 증명은 alignment 비용 합산의 정확성 주장과 다르다.",
        ),
        "observation_dataset": ReviewNote(
            "완료와 검열을 구별하는가?",
            "case-0=A0,B5,C10 완료12; case-1=A0,B5 검열12; 관측5",
            "양쪽 prefix AB; case-0 next C/5초, remaining7초; case-1 remaining 알 수 없음",
            "완료 사실은 명시 입력. 마지막 관측 이벤트를 완료로 간주하지 않는다.",
        ),
        "leakage_split": ReviewNote(
            "전이적으로 연결된 case가 분리되는가?",
            "0—1, 1—2 연결; 독립 case3; 두 partition",
            "{0,1,2}는 같은 partition; {3} 별도",
            "group 수 기준 분할이므로 case 비율은 정확히 50%가 아닐 수 있다.",
        ),
        "observation_encoder": ReviewNote(
            "미래 C가 학습 어휘에 들어가는가?",
            "case-0의 cutoff5까지 학습",
            "활동 어휘 A/B만; 미래 C 제외",
            "학습 case와 관측 cutoff를 고정한다.",
        ),
        "observation_matrix": ReviewNote(
            "held-out에도 같은 열을 사용하는가?",
            "동일 encoder로 AB 두 case 변환",
            "각 case에 A/B 행, 동일한 feature 열",
            "미관측 값은 알려진 0과 구별.",
        ),
        "case_sequence_tensor": ReviewNote(
            "padding을 이벤트와 구별하는가?",
            "AB 관측, 길이3 right padding",
            "각 행 event_mask=(True,True,False)",
            "padding과 missing feature를 서로 다른 mask로 보존.",
        ),
        "decision_evaluation": ReviewNote(
            "학습에서 분리된 case를 채점하는가?",
            "train:0→no,10→yes; held-out:10→yes",
            "held-out 정답 1/1, accuracy=1",
            "장난감 검산이며 실제 일반화 성능을 주장하지 않는다.",
        ),
        "drift_adjustment": ReviewNote(
            "동일한 관측에 변화 신호를 만드는가?",
            "A case 3개; adjacent windows; Holm",
            "원/보정 p=1, rejected 없음",
            "source-order offline 진단. p값은 변화의 원인이나 진실이 아니다.",
        ),
        "resource_simulation": ReviewNote(
            "단일 서버의 대기가 맞는가?",
            "동시 도착2건, 처리2초, capacity1",
            "완료2/4초; 대기0/2초",
            "비선점 고정 route 자원 시뮬레이션.",
        ),
        "resource_comparison": ReviewNote(
            "서버를 2개로 늘린 조건부 차이는?",
            "동일 cohort, capacity1 vs2",
            "평균 flow 3→2초, 차이 -1초",
            "가정에 따른 simulation 차이이며 인과효과 추정 아님.",
        ),
        "resource_duration_fit": ReviewNote(
            "관측 서비스 시간의 평균을 사용하는가?",
            "lifecycle start/complete duration2,4초",
            "관측수2, 평균3초",
            "exponential은 사용자 가정; 적합도 검증 아님.",
        ),
        "timed_playout": ReviewNote(
            "토큰을 시작에 예약하고 완료 후 내보내는가?",
            "p→A(2초)→q→B(3초)→r",
            "A 0→2초, B 2→5초; 종료5초",
            "예약/지연 출력 P/T profile. GSPN exponential race 모델이 아니다.",
        ),
        "case_stream_revision": ReviewNote(
            "늦은 B가 기존 직접 연결을 철회하는가?",
            "먼저 A1,C3; 나중에 B2",
            "A→C -1; A→B +1; B→C +1",
            "보유 facts를 재계산하는 revision 스트림.",
        ),
        "object_stream_revision": ReviewNote(
            "공유 이벤트가 실행을 합치는가?",
            "독립 객체 i1/i2에 bridge event 추가",
            "기존 실행2개→1개",
            "연결성 기반 execution 정의; qualifier는 보존.",
        ),
        "action_plan": ReviewNote(
            "선행 제약을 지킨 최소 완료시간은?",
            "A duration2µs→B duration1µs",
            "makespan=3µs, optimal",
            "유한 명시 입력에 대한 계획. 실제 실행/안전 보증 아님.",
        ),
        "action_matches": ReviewNote(
            "명시 패턴의 모든 witness를 기록하는가?",
            "fault interval1개, repair 패턴1개",
            "후보1개, 매핑 f→fault-1, 완전 탐색",
            "후보는 제안이며 자동 실행하지 않는다; no-op의 hard constraint는 planner에서 검사.",
        ),
        "operational_impact": ReviewNote(
            "공유 이벤트를 한 번만 세는가?",
            "i1/i2 동시 A 발화, cutoff0→1",
            "prior 객체2→0(-2), posterior0→2(+2), 이벤트1개",
            "모델 replay가 정당화한 marking 차이; 실제 세계의 인과효과 아님.",
        ),
        "object_subprocess": ReviewNote(
            "객체 타입별 경계를 정확히 자르는가?",
            "Item 타입 p→A→q 구간",
            "place p/q, transition a; 종료 r 토큰은 외부 ledger에 남음",
            "projection은 전체 OCPN synchronization 언어 보존을 보장하지 않는다.",
        ),
        "object_subprocess_pipeline": ReviewNote(
            "구간 추출의 단계 근거를 보존하는가?",
            "Item projection→p/q boundary",
            "최종 구간 p→A→q; 제거 q→B→r 근거 보존",
            "후속 hiding/reduction을 지정하지 않은 최소 pipeline.",
        ),
        "object_k_step": ReviewNote(
            "입력과 미래 target을 명시적으로 분리하는가?",
            "독립 Order5개, 각 x→2x+1, k1/horizon1",
            "독립 sample5개, 각 입력1개/미래 target1개",
            "시간 동률은 임의 event ID 순서로 확정하지 않는다.",
        ),
        "object_feature_inverse": ReviewNote(
            "학습 통계로 변환한 값을 되돌리는가?",
            "동일 amount feature를 표준화 후 역변환",
            "원래 amount의 근사 실수 복원",
            "정수 원래 타입/큰 정수의 완전한 정밀도 복원 보장은 아니다.",
        ),
        "object_regression_fit": ReviewNote(
            "알려진 직선을 찾는가?",
            "train x=0,1,2,3; target=2x+1",
            "계수2, 절편1",
            "QR OLS이며 일반 AutoML/비선형 예측 지원을 뜻하지 않는다.",
        ),
        "object_regression_predict": ReviewNote(
            "독립 held-out 객체를 예측하는가?",
            "학습에 없는 Order4, x4",
            "예측9",
            "공유 객체/event overlap 검사를 통과한 명시 평가 범위.",
        ),
        "object_regression_evaluation": ReviewNote(
            "관측 정답으로 MAE 분모를 확인하는가?",
            "held-out 예측9 vs 정답9",
            "평가수1, MAE≈0",
            "장난감 예제의 산술 확인. 실제 데이터 예측 품질은 알 수 없음.",
        ),
    }


def review_observations(cases: dict[str, ComputationResult]) -> dict[str, object]:
    """Small actual-value excerpts for domain readers; full JSON remains linked."""
    value = {name: result.value for name, result in cases.items()}
    return {
        "strict_inductive": asdict(value["strict_inductive"]),
        "coverability": {
            "bounded": value["coverability"].bounded,
            "target_coverable": value["coverability"].target_coverable,
            "place_bounds": [asdict(row) for row in value["coverability"].place_bounds],
        },
        "powl_to_tree": asdict(value["powl_to_tree"].model),
        "transition_bordered": {
            "visible_labels": [
                t.activity
                for t in value["transition_bordered"].model.transitions
                if t.activity
            ],
            "borders": len(value["transition_bordered"].borders),
        },
        "trie_to_net": {
            "trace_count": value["trie_to_net"].trace_count,
            "terminal_prefixes": [
                list(row.context)
                for row in value["trie_to_net"].state_mappings
                if row.final_count
            ],
        },
        "activity_labels": [
            asdict(row) for row in value["activity_labels"].occurrences
        ],
        "rename_labels": [asdict(row) for row in value["rename_labels"].changes],
        "maximal_decomposition": {
            "components": len(value["maximal_decomposition"].components),
            "shared_transitions": [
                asdict(row) for row in value["maximal_decomposition"].shared_transitions
            ],
            "identical_structure": value[
                "maximal_decomposition"
            ].certificate.identical_structure,
            "identical_markings": value[
                "maximal_decomposition"
            ].certificate.identical_markings,
        },
        "maximal_recomposition": {
            "equals_source": value["maximal_recomposition"] == _sequence_net()
        },
        "observation_dataset": {
            "prefixes": [
                asdict(row.prefix) for row in value["observation_dataset"].samples
            ],
            "targets": [asdict(row) for row in value["observation_dataset"].targets],
        },
        "leakage_split": asdict(value["leakage_split"]),
        "observation_encoder": {
            "columns": [
                asdict(row) for row in value["observation_encoder"].fitted_model.columns
            ]
        },
        "observation_matrix": asdict(value["observation_matrix"]),
        "case_sequence_tensor": {
            "rows": [asdict(row) for row in value["case_sequence_tensor"].rows]
        },
        "decision_evaluation": {
            "accuracy": str(
                value["decision_evaluation"].occurrence_accuracy.as_fraction()
            ),
            "confusion": [
                asdict(row) for row in value["decision_evaluation"].confusion
            ],
        },
        "drift_adjustment": {
            "family_size": value["drift_adjustment"].family_size,
            "adjusted_p_values": [
                str(row.adjusted_p_value.as_fraction())
                for row in value["drift_adjustment"].windows
            ],
            "rejected_boundaries": value["drift_adjustment"].rejected_boundaries,
        },
        "resource_simulation": {
            "completion_seconds": [
                row.completion_seconds
                for row in value["resource_simulation"].repetitions[0].events
            ],
            "waiting_seconds": [
                row.waiting_seconds
                for row in value["resource_simulation"].repetitions[0].events
            ],
        },
        "resource_comparison": [
            asdict(row) for row in value["resource_comparison"].differences
        ],
        "resource_duration_fit": [
            asdict(row) for row in value["resource_duration_fit"].activities
        ],
        "timed_playout": {
            "events": [asdict(row) for row in value["timed_playout"].runs[0].events],
            "completion_seconds": value["timed_playout"].runs[0].completion_seconds,
        },
        "case_stream_revision": {
            "edges": [asdict(row) for row in value["case_stream_revision"].dfg.edges],
            "changes": [asdict(row) for row in value["case_stream_revision"].changes],
            "issues": [issue.code for issue in cases["case_stream_revision"].issues],
        },
        "object_stream_revision": {
            "execution_count": len(
                value["object_stream_revision"].executions.executions
            )
        },
        "action_plan": {
            "outcome": value["action_plan"].outcome,
            "objective_value_us": value["action_plan"].objective_value,
            "no_action_feasible": value["action_plan"].no_action_feasible,
        },
        "action_matches": {
            "alternatives": len(value["action_matches"].alternatives),
            "matching_complete": value["action_matches"].matching_complete,
        },
        "operational_impact": {
            "processed_events": value[
                "operational_impact"
            ].scenario.processed_event_ids,
            "prior_delta": value["operational_impact"]
            .typed_deltas[0]
            .prior.total_count,
            "posterior_delta": value["operational_impact"]
            .typed_deltas[0]
            .posterior.total_count,
        },
        "object_subprocess": {
            "places": [p.id for p in value["object_subprocess"].model.places],
            "transitions": [t.id for t in value["object_subprocess"].model.transitions],
            "omitted_final_marking": asdict(
                value["object_subprocess"].omitted_final_marking
            ),
        },
        "object_subprocess_pipeline": {
            "profile_places": [
                p.id for p in value["object_subprocess_pipeline"].profile.model.places
            ],
            "boundary_removed_places": value[
                "object_subprocess_pipeline"
            ].boundary_removed_place_ids,
        },
        "object_k_step": {
            "samples": len(value["object_k_step"].samples),
            "k": value["object_k_step"].k,
            "horizon": value["object_k_step"].horizon,
        },
        "object_feature_inverse": {
            "numeric_values": sorted(
                row.cells[0].real for row in value["object_feature_inverse"].rows
            )
        },
        "object_regression_fit": {
            "coefficients": value["object_regression_fit"].coefficients,
            "intercepts": value["object_regression_fit"].intercepts,
        },
        "object_regression_predict": {
            "predictions": [
                row.values for row in value["object_regression_predict"].rows
            ]
        },
        "object_regression_evaluation": {
            "evaluated_count": value["object_regression_evaluation"]
            .targets[0]
            .evaluated_count,
            "mae": value["object_regression_evaluation"].targets[0].mean_absolute_error,
        },
    }


def build_exchange_examples() -> dict[str, dict]:
    """Model XML exchange examples, separate from ComputationResult persistence."""
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    bpmn = SplitBPMN(
        (
            SplitBPMNNode("start", "start_event"),
            SplitBPMNNode("task", "task", "A"),
            SplitBPMNNode("end", "end_event"),
        ),
        (SplitBPMNFlow("f0", "start", "task"), SplitBPMNFlow("f1", "task", "end")),
        "start",
        "end",
    )
    output = {}
    for name, model, dump, load in (
        ("pnml", _sequence_net(), dumps_pnml, loads_pnml),
        ("ptml", tree, dumps_ptml, loads_ptml),
        ("bpmn", bpmn, dumps_bpmn, loads_bpmn),
    ):
        document = dump(model)
        parsed = load(document)
        output[name] = {
            "document": document,
            "profile": parsed.profile,
            "semantic_roundtrip_equal": parsed.model == model,
            "second_roundtrip_equal": load(dump(parsed)).model == model,
        }
    return output


def build_extended_net_examples() -> dict[str, object]:
    """Hand calculations for firing primitives that return raw typed models."""
    base = PetriNet(
        tuple(Place(p) for p in ("p", "q", "r")),
        (Transition("t", "Finish"),),
        (Arc("p", "t", 2), Arc("t", "p", 3), Arc("t", "q", 4)),
        Marking(),
        Marking((("q", 1),)),
    )
    net = ResetInhibitorNet(base, (ResetArc("q", "t"),), (InhibitorArc("r", "t", 2),))
    before = Marking((("p", 2), ("q", 12), ("r", 1)))
    blocked = Marking((("p", 2), ("q", 12), ("r", 2)))
    choice = PetriNet(
        (Place("p"), Place("q")),
        (Transition("a", "Fast"), Transition("b", "Slow")),
        (Arc("p", "a"), Arc("a", "q"), Arc("p", "b"), Arc("b", "q")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )
    stochastic = StochasticPetriNet(
        choice,
        (
            StochasticTransition("a", 1, DurationDistribution("fixed", 2)),
            StochasticTransition("b", 3, DurationDistribution("fixed", 8)),
        ),
    )
    deterministic = StochasticPetriNet(
        choice,
        (
            StochasticTransition("a", 0, DurationDistribution("fixed", 2)),
            StochasticTransition("b", 3, DurationDistribution("fixed", 8)),
        ),
    )
    step = sample_stochastic_step(deterministic, choice.initial_marking, seed=0)
    return {
        "reset_inhibitor": {
            "input": before.tokens,
            "enabled": reset_inhibitor_is_enabled(net, before, "t"),
            "after": fire_reset_inhibitor(net, before, "t").tokens,
            "inhibitor_at_threshold_enabled": reset_inhibitor_is_enabled(
                net, blocked, "t"
            ),
        },
        "stochastic_choice": {
            "weights": (("a", 1), ("b", 3)),
            "probabilities": stochastic_transition_probabilities(
                stochastic, choice.initial_marking
            ),
            "zero_weight_step": asdict(step),
        },
    }


def write_review(output_directory: Path) -> dict[str, ComputationResult]:
    """Write portable JSON and a Korean domain-review report, without timestamps."""
    cases = build_review_cases()
    notes = review_notes()
    observations = review_observations(cases)
    if cases.keys() != notes.keys() or cases.keys() != observations.keys():
        raise ValueError("Every review result requires exactly one domain note")
    output_directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PIX 모델·W4 재현 가능한 도메인 검토",
        "",
        "이 문서는 작은 명시 입력의 실제 계산 결과입니다. PM4Py/OCPA 동등성, 운영 성능 또는 Schumpeter 실행 승인을 뜻하지 않습니다.",
        "검토 기준은 각 사례의 독립 기대값입니다. 기대값 불일치 또는 의미 계약이 달라지면 해당 판단을 철회하고 재검토해야 합니다.",
        "유효 범위: 이 실행이 저장한 결과의 operator/version/spec/source digest. 운영 규모의 시간·메모리·예측 성능은 알 수 없습니다.",
        "",
    ]
    for name, result in cases.items():
        encoded = result_json_bytes(result)
        (output_directory / f"{name}.json").write_bytes(encoded)
        note = notes[name]
        lines.extend(
            [
                f"## {name}",
                "",
                f"**질문:** {note.question}",
                "",
                f"입력: {note.inputs}",
                "",
                f"독립 기대값: {note.expected}",
                "",
                f"계산 상태: `{result.status.value}` / `{result.operator_id}`",
                "",
                f"해석 범위: {note.scope}",
                "",
                f"[전체 실제 결과와 provenance]({name}.json)",
                "",
                "```json",
                json.dumps(observations[name], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    exchanges = build_exchange_examples()
    lines.extend(
        [
            "## 모델 교환",
            "",
            "PNML: weighted P/T net, PTML: 선언한 tree profile, BPMN: task/XOR/AND 제한 profile. 의미 동등 roundtrip을 확인하며 XML byte identity는 요구하지 않습니다.",
            "",
        ]
    )
    for name, exchange in exchanges.items():
        document = exchange.pop("document")
        if isinstance(document, str):
            document = document.encode("utf-8")
        (output_directory / f"model.{name}").write_bytes(document)
        lines.extend(
            [
                f"[{name.upper()} 출력](model.{name})",
                "",
                "```json",
                json.dumps(exchange, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    extended = build_extended_net_examples()
    lines.extend(
        [
            "## 확장 net 발화",
            "",
            "기대값: p의 일반입력2/출력3은 p=3, q reset 후 출력4는 q=4, r=1은 보존. r=2에서는 inhibitor가 막습니다. 선택 가중치1:3은 확률0.25:0.75이며, 가중치0인 a는 선택되지 않습니다.",
            "",
            "범위: 명시 reset/inhibitor와 local weighted choice 의미. 일반 P/T 분석으로 special arc를 제거해 처리하지 않습니다.",
            "",
            "```json",
            json.dumps(extended, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    (output_directory / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (output_directory / "review-notes.json").write_text(
        json.dumps(
            {name: asdict(note) for name, note in notes.items()},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_directory / "actual-summary.json").write_text(
        json.dumps(observations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path(".artifacts/2026-09-17-implementation-models-w4/review"),
    )
    args = parser.parse_args()
    cases = write_review(args.output_directory)
    print(f"Wrote {len(cases)} native results and REVIEW.md to {args.output_directory}")


if __name__ == "__main__":
    main()
