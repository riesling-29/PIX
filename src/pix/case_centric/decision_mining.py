"""Witness-based decision observations and typed data Petri-net guards.

Structural choice places are places with multiple outgoing transition IDs. A
record is a selected replay/alignment firing, not a causal explanation or proof
that all optimal witnesses choose the same branch. Numeric event attributes are
observed strictly before that firing. Case attributes enter only through an
explicit caller declaration that they were available at case start.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from math import isfinite
from typing import ClassVar, Literal

from pix.case_centric.advanced import (
    DecisionExample,
    DecisionTree,
    DecisionTreeSpec,
    GuardCondition,
    mine_decision_tree,
)
from pix.compute.conformance import align_traces
from pix.compute.model_semantics import (
    enabled_transitions,
    fire,
    is_enabled,
    model_digest,
)
from pix.compute.replay import replay_traces
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.conformance import AlignmentSet, AlignmentSpec
from pix.contracts.models import Marking, PetriNet
from pix.contracts.replay import ReplaySet, ReplaySpec
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.event_log import CaseLog, CaseTrace, case_traces


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _numeric(value):
    return type(value) is int or (type(value) is float and isfinite(value))


def _strings(value, name):
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must contain unique entries")


def _result(operator, source, spec, value=None, issues=(), parents=(), status=None):
    status = status or (
        ComputeStatus.COMPUTED if value is not None else ComputeStatus.UNAVAILABLE
    )
    return ComputationResult(
        operator,
        "1.0.0",
        source,
        spec,
        status,
        value,
        issues,
        computation_identity(operator, "1.0.0", source, spec, parents),
        parents,
    )


def _payload_digest(value):
    if value is None:
        return None
    content = json.dumps(
        asdict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "pix.decision-evidence.v1:sha256:" + sha256(content).hexdigest()


@dataclass(frozen=True, slots=True)
class DecisionFeatureSpec:
    name: str
    attribute_key: str
    scope: Literal["event_prefix", "case_declared_initial"] = "event_prefix"

    def __post_init__(self):
        _text(self.name, "feature name")
        _text(self.attribute_key, "attribute key")
        if self.scope not in ("event_prefix", "case_declared_initial"):
            raise ValueError("unknown decision feature scope")


@dataclass(frozen=True, slots=True)
class DecisionTableSpec:
    features: tuple[DecisionFeatureSpec, ...]
    method: Literal["alignment", "replay"] = "alignment"
    places: tuple[str, ...] | None = None
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    alignment_spec: AlignmentSpec = AlignmentSpec()
    replay_spec: ReplaySpec = ReplaySpec()
    require_fitting_trace: bool = True
    include_silent: bool = True
    include_unobserved_model_moves: bool = False
    ambiguous_label_policy: Literal["exclude", "selected_witness"] = "exclude"
    max_rows: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.features, tuple) or not all(
            isinstance(feature, DecisionFeatureSpec) for feature in self.features
        ):
            raise TypeError("features must be a tuple of DecisionFeatureSpec")
        _strings(tuple(feature.name for feature in self.features), "feature names")
        if self.places is not None:
            _strings(self.places, "places")
            object.__setattr__(self, "places", tuple(sorted(self.places)))
        if self.method not in ("alignment", "replay"):
            raise ValueError("method must be alignment or replay")
        for name, kind in (
            ("trace_spec", CaseTraceSpec),
            ("alignment_spec", AlignmentSpec),
            ("replay_spec", ReplaySpec),
        ):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} has the wrong contract type")
        for name in (
            "require_fitting_trace",
            "include_silent",
            "include_unobserved_model_moves",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if self.ambiguous_label_policy not in ("exclude", "selected_witness"):
            raise ValueError("unknown ambiguous label policy")
        _integer(self.max_rows, "max_rows", 1)


@dataclass(frozen=True, slots=True)
class DecisionTableRequest:
    model_digest: str
    witness_computation_id: str | None
    parameters: DecisionTableSpec
    witness_payload_digest: str | None = None
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    place_id: str
    transition_ids: tuple[str, ...]

    def __post_init__(self):
        _text(self.place_id, "place_id")
        _strings(self.transition_ids, "transition_ids")
        if len(self.transition_ids) < 2:
            raise ValueError("a decision point needs at least two outgoing transitions")


@dataclass(frozen=True, slots=True)
class ObservedDecisionFeature:
    name: str
    value: int | float | None
    scope: str
    source_event_id: str | None
    source_event_index: int | None
    status: Literal["observed", "missing", "not_numeric"]

    def __post_init__(self):
        _text(self.name, "feature name")
        if self.scope not in (
            "event_prefix",
            "case_declared_initial",
        ) or self.status not in ("observed", "missing", "not_numeric"):
            raise ValueError("unknown decision feature scope/status")
        if self.status == "observed":
            if not _numeric(self.value):
                raise ValueError(
                    "observed decision features must be finite numeric values"
                )
        elif self.value is not None:
            raise ValueError("unobserved decision features cannot contain values")
        if self.scope == "case_declared_initial" or self.status == "missing":
            if self.source_event_id is not None or self.source_event_index is not None:
                raise ValueError(
                    "case-initial or missing observations have no source event"
                )
        else:
            _text(self.source_event_id, "source event id")
            _integer(self.source_event_index, "source event index")


@dataclass(frozen=True, slots=True)
class DecisionObservation:
    row_id: str
    case_id: str
    place_id: str
    transition_id: str
    activity: str | None
    event_id: str | None
    witness_step_index: int
    prefix_event_count: int
    marking_before: Marking
    enabled_branch_ids: tuple[str, ...]
    same_label_enabled_branch_ids: tuple[str, ...]
    features: tuple[ObservedDecisionFeature, ...]
    eligible: bool
    reasons: tuple[str, ...]

    def __post_init__(self):
        for name in ("row_id", "case_id", "place_id", "transition_id"):
            _text(getattr(self, name), name)
        for name in ("witness_step_index", "prefix_event_count"):
            _integer(getattr(self, name), name)
        if not isinstance(self.marking_before, Marking):
            raise TypeError("marking_before must be Marking")
        for name in ("enabled_branch_ids", "same_label_enabled_branch_ids", "reasons"):
            _strings(getattr(self, name), name)
        if self.transition_id not in self.enabled_branch_ids or not set(
            self.same_label_enabled_branch_ids
        ).issubset(self.enabled_branch_ids):
            raise ValueError(
                "selected/same-label branch IDs must be enabled alternatives"
            )
        if not isinstance(self.features, tuple) or not all(
            isinstance(feature, ObservedDecisionFeature) for feature in self.features
        ):
            raise TypeError("features must be observed decision features")
        _strings(tuple(feature.name for feature in self.features), "feature names")
        if type(self.eligible) is not bool or self.eligible != (not self.reasons):
            raise ValueError("eligibility must agree with exclusion reasons")
        for feature in self.features:
            if (
                feature.scope == "event_prefix"
                and feature.source_event_index is not None
            ):
                if (
                    feature.source_event_index >= self.prefix_event_count
                    or feature.source_event_id == self.event_id
                ):
                    raise ValueError(
                        "decision features must precede the selected firing event"
                    )
            if (
                feature.status != "observed"
                and "feature_" + feature.status + ":" + feature.name not in self.reasons
            ):
                raise ValueError(
                    "unobserved features require an explicit exclusion reason"
                )


@dataclass(frozen=True, slots=True)
class DecisionCaseExclusion:
    case_id: str
    reason: str

    def __post_init__(self):
        _text(self.case_id, "case_id")
        _text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class DecisionTable:
    model_digest: str
    features: tuple[DecisionFeatureSpec, ...]
    decision_points: tuple[DecisionPoint, ...]
    case_ids: tuple[str, ...]
    observations: tuple[DecisionObservation, ...]
    excluded_cases: tuple[DecisionCaseExclusion, ...]
    decision_occurrence_count: int
    omitted_row_count: int
    eligible_row_count: int
    witness_method: str
    witness_computation_id: str

    def __post_init__(self):
        _text(self.model_digest, "model_digest")
        _text(self.witness_computation_id, "witness_computation_id")
        _strings(self.case_ids, "case_ids")
        if self.witness_method not in ("alignment", "replay"):
            raise ValueError("unknown witness method")
        for name, item_type in (
            ("features", DecisionFeatureSpec),
            ("decision_points", DecisionPoint),
            ("observations", DecisionObservation),
            ("excluded_cases", DecisionCaseExclusion),
        ):
            if not isinstance(getattr(self, name), tuple) or not all(
                isinstance(item, item_type) for item in getattr(self, name)
            ):
                raise TypeError(f"{name} has invalid contract members")
        names = tuple(feature.name for feature in self.features)
        _strings(names, "feature names")
        _strings(
            tuple(point.place_id for point in self.decision_points),
            "decision point IDs",
        )
        _strings(tuple(row.row_id for row in self.observations), "observation IDs")
        _strings(
            tuple(case.case_id for case in self.excluded_cases), "excluded case IDs"
        )
        points = {
            point.place_id: point.transition_ids for point in self.decision_points
        }
        excluded = {case.case_id for case in self.excluded_cases}
        if not excluded.issubset(self.case_ids):
            raise ValueError("excluded cases are outside the table population")
        for row in self.observations:
            if (
                row.case_id not in self.case_ids
                or row.case_id in excluded
                or row.transition_id not in points.get(row.place_id, ())
            ):
                raise ValueError(
                    "decision observation lies outside its case/point population"
                )
            if tuple(feature.name for feature in row.features) != names or any(
                feature.scope != requested.scope
                for feature, requested in zip(row.features, self.features)
            ):
                raise ValueError(
                    "decision observation feature schema differs from its table"
                )
        for name in (
            "decision_occurrence_count",
            "omitted_row_count",
            "eligible_row_count",
        ):
            _integer(getattr(self, name), name)
        if self.decision_occurrence_count != len(
            self.observations
        ) + self.omitted_row_count or self.eligible_row_count != sum(
            row.eligible for row in self.observations
        ):
            raise ValueError(
                "decision table coverage counts disagree with observations"
            )


def discover_decision_points(net: PetriNet) -> tuple[DecisionPoint, ...]:
    """Structural fanout, including silent and duplicate-label transitions."""
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    points = []
    for place in net.places:
        transitions = tuple(
            sorted(arc.target for arc in net.arcs if arc.source == place.id)
        )
        if len(transitions) >= 2:
            points.append(DecisionPoint(place.id, transitions))
    return tuple(points)


@dataclass(frozen=True, slots=True)
class _Step:
    kind: str
    event_id: str | None
    transition_id: str | None
    before: Marking
    after: Marking
    inserted: tuple[tuple[str, int], ...]
    original_index: int


def _insert(marking, tokens):
    additions = Marking(tokens)
    present = dict(marking.tokens)
    for place, count in additions.tokens:
        present[place] = present.get(place, 0) + count
    return Marking(tuple(present.items()))


def _validate_path(net, trace, item, method):
    """Check actual firing/event correspondence, not global optimality again."""
    steps, current, consumed = [], net.initial_marking, 0
    activities = {transition.id: transition.activity for transition in net.transitions}
    deviating = False
    if method == "alignment":
        if item.event_ids != tuple(event.event_id for event in trace.events):
            raise ValueError("alignment event IDs do not match the case projection")
        raw = item.moves
    else:
        if item.event_count != len(trace.events) or item.processed_event_count != len(
            trace.events
        ):
            raise ValueError(
                "completed replay event counts do not match the projection"
            )
        raw = item.steps
        if not raw or raw[0].kind != "initial" or raw[-1].kind != "finalize":
            raise ValueError(
                "completed replay must have initial and finalize witnesses"
            )
    for index, original in enumerate(raw):
        if method == "replay" and original.kind == "initial":
            if (
                index != 0
                or original.marking_before != ()
                or Marking(original.marking_after) != current
            ):
                raise ValueError("invalid replay initial marking")
            continue
        if method == "replay" and original.kind == "finalize":
            if index != len(raw) - 1 or Marking(original.marking_before) != current:
                raise ValueError("invalid replay finalization position")
            if original.consumed_tokens != net.final_marking.tokens:
                raise ValueError("replay finalization must consume the target marking")
            repaired = dict(_insert(current, original.inserted_tokens).tokens)
            for place, count in net.final_marking.tokens:
                repaired[place] = repaired.get(place, 0) - count
            if any(count < 0 for count in repaired.values()):
                raise ValueError("invalid replay finalization deficit")
            expected = Marking(
                tuple((place, count) for place, count in repaired.items() if count)
            )
            if expected != Marking(original.marking_after):
                raise ValueError("invalid replay finalization marking")
            deviating |= current != net.final_marking or bool(original.inserted_tokens)
            continue
        if method == "alignment":
            kind, before, after, inserted = (
                original.kind,
                Marking(original.before_marking),
                Marking(original.after_marking),
                (),
            )
        else:
            kind = {
                "visible": "synchronous",
                "silent": "silent",
                "log_deviation": "log",
            }.get(original.kind)
            if kind is None:
                raise ValueError("unknown replay witness step")
            before, after, inserted = (
                Marking(original.marking_before),
                Marking(original.marking_after),
                original.inserted_tokens,
            )
        if before != current:
            raise ValueError("witness markings are not contiguous")
        event_id, transition_id = original.event_id, original.transition_id
        if kind in ("synchronous", "log"):
            if (
                consumed >= len(trace.events)
                or event_id != trace.events[consumed].event_id
            ):
                raise ValueError(
                    "witness consumes events outside the recorded case order"
                )
            if original.activity != trace.events[consumed].activity:
                raise ValueError("witness activity differs from the projected event")
        elif event_id is not None:
            raise ValueError("model-only/silent moves cannot consume an event")
        if kind == "log":
            if transition_id is not None or before != after or inserted:
                raise ValueError("log-only move cannot change the model marking")
            deviating = True
        elif kind in ("synchronous", "silent", "model"):
            if transition_id not in activities:
                raise ValueError("witness refers to an unknown transition")
            if kind == "silent" and activities[transition_id] is not None:
                raise ValueError("silent move refers to a visible transition")
            if kind in ("synchronous", "model") and activities[transition_id] is None:
                raise ValueError("visible move refers to a silent transition")
            if (
                kind == "synchronous"
                and activities[transition_id] != trace.events[consumed].activity
            ):
                raise ValueError("synchronous transition and event activities differ")
            repaired = _insert(before, inserted)
            net.validate_marking(repaired)
            if (
                not is_enabled(net, repaired, transition_id)
                or fire(net, repaired, transition_id) != after
            ):
                raise ValueError("witness does not represent a valid model firing")
            deviating |= kind == "model" or bool(inserted)
        else:
            raise ValueError("unknown alignment move kind")
        steps.append(
            _Step(kind, event_id, transition_id, before, after, inserted, index)
        )
        current = after
        if event_id is not None:
            consumed += 1
    if consumed != len(trace.events):
        raise ValueError("completed witness did not consume every case event")
    if method == "alignment" and current != net.final_marking:
        raise ValueError("optimal alignment witness does not end at the final marking")
    return tuple(steps), not deviating


def _feature_observation(log, trace, feature, prefix):
    source_id, source_index = None, None
    if feature.scope == "case_declared_initial":
        attribute = log.attribute(trace, feature.attribute_key)
    else:
        attribute = None
        for index, event in enumerate(prefix):
            observed = log.attribute(event, feature.attribute_key)
            if observed is not None:
                attribute, source_id, source_index = observed, event.id, index
    if attribute is None:
        return ObservedDecisionFeature(
            feature.name, None, feature.scope, source_id, source_index, "missing"
        )
    if attribute.type not in ("int", "float") or not _numeric(attribute.value):
        return ObservedDecisionFeature(
            feature.name, None, feature.scope, source_id, source_index, "not_numeric"
        )
    return ObservedDecisionFeature(
        feature.name,
        attribute.value,
        feature.scope,
        source_id,
        source_index,
        "observed",
    )


def extract_decision_table(
    log: CaseLog,
    net: PetriNet,
    spec: DecisionTableSpec,
    *,
    witness: ComputationResult[AlignmentSet | ReplaySet] | None = None,
) -> ComputationResult[DecisionTable]:
    """Extract branch IDs using real native replay/alignment firing witnesses.

    Same-label enabled branches are excluded by default rather than collapsing
    transition identity into activity text. With selected_witness policy the
    exact transition ID and alternative IDs remain in the observation. Silent
    decisions inherit the consumed-event prefix before their firing.
    """
    if (
        not isinstance(log, CaseLog)
        or not isinstance(net, PetriNet)
        or not isinstance(spec, DecisionTableSpec)
    ):
        raise TypeError("expected CaseLog, PetriNet and DecisionTableSpec")
    traces = case_traces(log, spec.trace_spec)
    digest, operator = model_digest(net), "pix.case_centric.extract_decision_table"
    if witness is None and traces.status is ComputeStatus.COMPUTED:
        witness = (
            align_traces(traces, net, spec.alignment_spec)
            if spec.method == "alignment"
            else replay_traces(traces, net, spec.replay_spec)
        )
    if witness is not None and not isinstance(witness, ComputationResult):
        raise TypeError("witness must be a ComputationResult")
    request = DecisionTableRequest(
        digest,
        witness.computation_id if witness else None,
        spec,
        _payload_digest(witness.value) if witness else None,
    )
    parents = tuple(
        item.computation_id
        for item in (traces, witness)
        if item is not None and item.computation_id
    )
    if traces.status is not ComputeStatus.COMPUTED:
        return _result(
            operator,
            traces.source_digest,
            request,
            issues=traces.issues,
            parents=parents,
            status=ComputeStatus.INVALID_INPUT,
        )
    expected_type, expected_operator = (
        (AlignmentSet, "pix.align_traces")
        if spec.method == "alignment"
        else (ReplaySet, "pix.replay_traces")
    )
    if (
        witness.operator_id != expected_operator
        or witness.source_digest != traces.source_digest
        or traces.computation_id not in witness.parent_computation_ids
        or getattr(witness.spec, "model_digest", None) != digest
        or getattr(witness.spec, "parameters", None)
        != (spec.alignment_spec if spec.method == "alignment" else spec.replay_spec)
    ):
        raise ValueError(
            "witness model, source projection or operator identity does not match the request"
        )
    expected_identity = computation_identity(
        witness.operator_id,
        witness.operator_version,
        witness.source_digest,
        witness.spec,
        witness.parent_computation_ids,
    )
    if expected_identity != witness.computation_id:
        raise ValueError("witness computation identity is inconsistent")
    if witness.value is None:
        return _result(
            operator,
            traces.source_digest,
            request,
            issues=witness.issues
            or (ComputeIssue("witness_unavailable", "No firing witness is available"),),
            parents=parents,
        )
    if (
        not isinstance(witness.value, expected_type)
        or witness.value.model_digest != digest
    ):
        raise ValueError("witness payload does not match its model and method")
    points = discover_decision_points(net)
    if spec.places is not None:
        if not set(spec.places).issubset(point.place_id for point in points):
            raise ValueError("selected places must be structural choice places")
        points = tuple(point for point in points if point.place_id in spec.places)
    records = (
        witness.value.alignments if spec.method == "alignment" else witness.value.traces
    )
    projected = {trace.object_id: trace for trace in traces.value.traces}
    original = {trace.id: trace for trace in log.traces}
    if len(records) != len(projected) or {item.object_id for item in records} != set(
        projected
    ):
        raise ValueError("witness must cover each projected case exactly once")
    by_case = {item.object_id: item for item in records}
    records = tuple(by_case[trace.object_id] for trace in traces.value.traces)
    activities = {transition.id: transition.activity for transition in net.transitions}
    rows, excluded, occurrence_count = [], [], 0
    for item in records:
        complete = item.status == (
            "optimal" if spec.method == "alignment" else "completed"
        )
        if not complete:
            excluded.append(DecisionCaseExclusion(item.object_id, item.status))
            continue
        steps, fitting = _validate_path(
            net, projected[item.object_id], item, spec.method
        )
        if spec.require_fitting_trace and not fitting:
            excluded.append(DecisionCaseExclusion(item.object_id, "nonfitting_witness"))
            continue
        trace = original[item.object_id]
        prefix = []
        for step in steps:
            if step.transition_id is not None:
                for point in points:
                    if step.transition_id not in point.transition_ids:
                        continue
                    occurrence_count += 1
                    if len(rows) >= spec.max_rows:
                        continue
                    repaired = _insert(step.before, step.inserted)
                    enabled = tuple(
                        tid
                        for tid in enabled_transitions(net, repaired)
                        if tid in point.transition_ids
                    )
                    same_label = tuple(
                        tid
                        for tid in enabled
                        if activities[tid] == activities[step.transition_id]
                    )
                    features = tuple(
                        _feature_observation(log, trace, feature, prefix)
                        for feature in spec.features
                    )
                    reasons = []
                    if step.inserted:
                        reasons.append("repaired_marking")
                    if not spec.include_silent and step.kind == "silent":
                        reasons.append("silent_excluded")
                    if not spec.include_unobserved_model_moves and step.kind == "model":
                        reasons.append("unobserved_model_move")
                    if (
                        step.kind != "silent"
                        and len(same_label) > 1
                        and spec.ambiguous_label_policy == "exclude"
                    ):
                        reasons.append("ambiguous_transition_label")
                    reasons.extend(
                        "feature_" + feature.status + ":" + feature.name
                        for feature in features
                        if feature.status != "observed"
                    )
                    row_id = "decision:" + json.dumps(
                        (trace.id, point.place_id, step.original_index),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    rows.append(
                        DecisionObservation(
                            row_id,
                            trace.id,
                            point.place_id,
                            step.transition_id,
                            activities[step.transition_id],
                            step.event_id,
                            step.original_index,
                            len(prefix),
                            step.before,
                            enabled,
                            same_label,
                            features,
                            not reasons,
                            tuple(reasons),
                        )
                    )
            if step.event_id is not None:
                # Source order was verified above; the current event only
                # becomes visible after the corresponding decision record.
                prefix.append(trace.events[len(prefix)])
    omitted = occurrence_count - len(rows)
    eligible = sum(row.eligible for row in rows)
    value = DecisionTable(
        digest,
        spec.features,
        points,
        tuple(sorted(projected)),
        tuple(rows),
        tuple(excluded),
        occurrence_count,
        omitted,
        eligible,
        spec.method,
        witness.computation_id,
    )
    issues = []
    if excluded:
        issues.append(
            ComputeIssue(
                "decision_cases_excluded",
                f"{len(excluded)} cases lacked an eligible completed witness",
            )
        )
    if eligible != len(rows):
        issues.append(
            ComputeIssue(
                "decision_rows_ineligible",
                f"{len(rows) - eligible} rows retain missing/ambiguous observation evidence",
            )
        )
    if omitted:
        issues.append(
            ComputeIssue(
                "decision_row_limit",
                f"{omitted} decision observations omitted by max_rows",
            )
        )
    return _result(
        operator,
        traces.source_digest,
        request,
        value,
        tuple(issues),
        parents,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
    )


@dataclass(frozen=True, slots=True)
class DataGuardClause:
    """Conjunction; the empty conjunction is true."""

    conditions: tuple[GuardCondition, ...]

    def __post_init__(self):
        if not isinstance(self.conditions, tuple) or not all(
            isinstance(item, GuardCondition) for item in self.conditions
        ):
            raise TypeError("conditions must be a tuple of GuardCondition")


@dataclass(frozen=True, slots=True)
class TransitionDataGuard:
    """Disjunction of clauses; an empty disjunction is false."""

    transition_id: str
    clauses: tuple[DataGuardClause, ...]
    support: int

    def __post_init__(self):
        _text(self.transition_id, "transition_id")
        if not isinstance(self.clauses, tuple) or not all(
            isinstance(item, DataGuardClause) for item in self.clauses
        ):
            raise TypeError("clauses must be a tuple of DataGuardClause")
        _integer(self.support, "support")


@dataclass(frozen=True, slots=True)
class DecisionPointModel:
    place_id: str
    transition_ids: tuple[str, ...]
    training_row_ids: tuple[str, ...]
    training_case_ids: tuple[str, ...]
    tree: DecisionTree | None
    guards: tuple[TransitionDataGuard, ...]
    status: Literal["fitted", "resource_limit", "untrained"]

    def __post_init__(self):
        _text(self.place_id, "place_id")
        for name in ("transition_ids", "training_row_ids", "training_case_ids"):
            _strings(getattr(self, name), name)
        if self.status not in ("fitted", "resource_limit", "untrained"):
            raise ValueError("unknown point model status")
        if not isinstance(self.guards, tuple) or not all(
            isinstance(guard, TransitionDataGuard) for guard in self.guards
        ):
            raise TypeError("guards must be a tuple of TransitionDataGuard")
        if self.status == "untrained":
            if self.tree is not None or self.guards:
                raise ValueError("untrained points cannot carry fitted guards")
        elif (
            not isinstance(self.tree, DecisionTree)
            or set(guard.transition_id for guard in self.guards)
            != set(self.transition_ids)
            or len(self.guards) != len(self.transition_ids)
        ):
            raise ValueError(
                "trained points require one guard per outgoing transition and a tree"
            )
        elif (
            self.tree.training_count != len(self.training_row_ids)
            or self.tree.status != self.status
            or not {label for label, _ in self.tree.nodes[0].class_counts}.issubset(
                self.transition_ids
            )
        ):
            raise ValueError(
                "point model training population/status/targets differ from its tree"
            )


@dataclass(frozen=True, slots=True)
class DataPetriNet:
    """An accepting Petri net with typed numeric guards at selected decisions.

    Distinct decision-place guards affecting one transition are conjoined.
    Untrained decisions evaluate as unknown. Transitions outside every selected
    decision retain their ordinary structural enabling semantics. The model
    neither executes arbitrary expressions nor treats a missing value as zero.
    """

    base: PetriNet
    features: tuple[DecisionFeatureSpec, ...]
    decisions: tuple[DecisionPointModel, ...]
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.base, PetriNet):
            raise TypeError("base must be PetriNet")
        if not isinstance(self.features, tuple) or not all(
            isinstance(feature, DecisionFeatureSpec) for feature in self.features
        ):
            raise TypeError("features must be a tuple of DecisionFeatureSpec")
        names = tuple(feature.name for feature in self.features)
        _strings(names, "feature names")
        if not isinstance(self.decisions, tuple) or not all(
            isinstance(point, DecisionPointModel) for point in self.decisions
        ):
            raise TypeError("decisions must be a tuple of DecisionPointModel")
        if len({point.place_id for point in self.decisions}) != len(self.decisions):
            raise ValueError("decision places must be unique")
        structural = {
            point.place_id: point.transition_ids
            for point in discover_decision_points(self.base)
        }
        for point in self.decisions:
            if (
                point.place_id not in structural
                or tuple(sorted(point.transition_ids)) != structural[point.place_id]
            ):
                raise ValueError(
                    "point model outgoing transitions differ from the base net"
                )
            if point.tree is not None and point.tree.feature_names != names:
                raise ValueError(
                    "decision tree feature schema differs from DataPetriNet"
                )
            for guard in point.guards:
                for clause in guard.clauses:
                    for condition in clause.conditions:
                        if (
                            type(condition.feature_index) is not int
                            or not 0 <= condition.feature_index < len(names)
                            or names[condition.feature_index] != condition.feature_name
                            or condition.operator not in ("<=", ">")
                            or not _numeric(condition.threshold)
                        ):
                            raise ValueError(
                                "guard contains an invalid typed numeric condition"
                            )


def data_petri_net_digest(model: DataPetriNet) -> str:
    if not isinstance(model, DataPetriNet):
        raise TypeError("model must be DataPetriNet")
    content = json.dumps(
        asdict(model),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "pix.data-petri-net.v1:sha256:" + sha256(content).hexdigest()


@dataclass(frozen=True, slots=True)
class DataPetriNetMiningSpec:
    """Case IDs select all of their decision occurrences as one training group."""

    training_case_ids: tuple[str, ...] | None = None
    max_depth: int = 8
    min_leaf: int = 1
    min_gain: int | float = 0.0
    max_examples: int = 10_000
    max_split_evaluations: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.training_case_ids is not None:
            _strings(self.training_case_ids, "training_case_ids")
            object.__setattr__(
                self, "training_case_ids", tuple(sorted(self.training_case_ids))
            )
        DecisionTreeSpec(
            (),
            self.max_depth,
            self.min_leaf,
            self.min_gain,
            self.max_examples,
            self.max_split_evaluations,
        )


@dataclass(frozen=True, slots=True)
class DataPetriNetMiningRequest:
    table_computation_id: str | None
    model_digest: str
    parameters: DataPetriNetMiningSpec
    table_payload_digest: str | None = None
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DataPetriNetMining:
    model: DataPetriNet
    training_case_ids: tuple[str, ...]
    training_observation_count: int
    excluded_training_observation_count: int
    tree_computation_ids: tuple[str, ...]


def mine_data_petri_net(
    table: ComputationResult[DecisionTable],
    net: PetriNet,
    spec: DataPetriNetMiningSpec = DataPetriNetMiningSpec(),
) -> ComputationResult[DataPetriNetMining]:
    """Fit a separate CART per decision place using eligible training rows only."""
    if (
        not isinstance(table, ComputationResult)
        or not isinstance(net, PetriNet)
        or not isinstance(spec, DataPetriNetMiningSpec)
    ):
        raise TypeError(
            "expected decision table result, PetriNet and DataPetriNetMiningSpec"
        )
    digest, operator = model_digest(net), "pix.case_centric.mine_data_petri_net"
    request = DataPetriNetMiningRequest(
        table.computation_id, digest, spec, _payload_digest(table.value)
    )
    parents = (table.computation_id,) if table.computation_id else ()
    if table.value is None:
        return _result(
            operator,
            table.source_digest,
            request,
            issues=table.issues
            or (
                ComputeIssue(
                    "decision_table_unavailable", "No decision table is available"
                ),
            ),
            parents=parents,
        )
    if (
        table.operator_id != "pix.case_centric.extract_decision_table"
        or not isinstance(table.value, DecisionTable)
        or table.value.model_digest != digest
    ):
        raise ValueError("decision table model or operator differs from the request")
    if table.computation_id != computation_identity(
        table.operator_id,
        table.operator_version,
        table.source_digest,
        table.spec,
        table.parent_computation_ids,
    ):
        raise ValueError("decision table computation identity is inconsistent")
    data = table.value
    selected = set(
        data.case_ids if spec.training_case_ids is None else spec.training_case_ids
    )
    if not selected.issubset(data.case_ids):
        raise ValueError("training selection contains unknown case IDs")
    names = tuple(feature.name for feature in data.features)
    tree_spec = DecisionTreeSpec(
        names,
        spec.max_depth,
        spec.min_leaf,
        spec.min_gain,
        spec.max_examples,
        spec.max_split_evaluations,
    )
    points, tree_ids, fitted_rows, excluded_rows = [], [], 0, 0
    issues = []
    for point in data.decision_points:
        selected_rows = tuple(
            row
            for row in data.observations
            if row.place_id == point.place_id and row.case_id in selected
        )
        rows = tuple(row for row in selected_rows if row.eligible)
        excluded_rows += len(selected_rows) - len(rows)
        if any(
            row.transition_id not in point.transition_ids
            or len(row.features) != len(names)
            or tuple(feature.name for feature in row.features) != names
            or any(not _numeric(feature.value) for feature in row.features)
            for row in rows
        ):
            raise ValueError(
                "eligible decision observations contain invalid labels/features"
            )
        if not rows:
            points.append(
                DecisionPointModel(
                    point.place_id, point.transition_ids, (), (), None, (), "untrained"
                )
            )
            issues.append(
                ComputeIssue(
                    "untrained_decision_point",
                    "No eligible observations exist in the training selection",
                    ("place", point.place_id),
                )
            )
            continue
        # CART samples are decision occurrences, not original cases. The wrapper
        # retains original case grouping for all fit/holdout selection decisions.
        occurrence_log = CaseLog(tuple(CaseTrace(row.row_id) for row in rows))
        examples = tuple(
            DecisionExample(
                row.row_id,
                tuple(feature.value for feature in row.features),
                row.transition_id,
            )
            for row in rows
        )
        fitted = mine_decision_tree(occurrence_log, examples, tree_spec)
        if fitted.computation_id:
            tree_ids.append(fitted.computation_id)
        if fitted.value is None:
            points.append(
                DecisionPointModel(
                    point.place_id, point.transition_ids, (), (), None, (), "untrained"
                )
            )
            issues.append(
                ComputeIssue(
                    "decision_tree_unavailable",
                    "Tree fitting did not produce a model",
                    ("place", point.place_id),
                )
            )
            continue
        guards = tuple(
            TransitionDataGuard(
                transition_id,
                tuple(
                    DataGuardClause(guard.conditions)
                    for guard in fitted.value.guards
                    if guard.prediction == transition_id
                ),
                sum(row.transition_id == transition_id for row in rows),
            )
            for transition_id in point.transition_ids
        )
        point_status = (
            "fitted" if fitted.status is ComputeStatus.COMPUTED else "resource_limit"
        )
        points.append(
            DecisionPointModel(
                point.place_id,
                point.transition_ids,
                tuple(sorted(row.row_id for row in rows)),
                tuple(sorted({row.case_id for row in rows})),
                fitted.value,
                guards,
                point_status,
            )
        )
        fitted_rows += len(rows)
        if fitted.status is not ComputeStatus.COMPUTED:
            issues.append(
                ComputeIssue(
                    "decision_tree_partial",
                    "Tree resource limit retained majority leaves",
                    ("place", point.place_id),
                )
            )
    if excluded_rows:
        issues.append(
            ComputeIssue(
                "ineligible_training_observations",
                f"{excluded_rows} selected observations were not eligible",
            )
        )
    excluded_cases = sum(case.case_id in selected for case in data.excluded_cases)
    if excluded_cases or data.omitted_row_count:
        issues.append(
            ComputeIssue(
                "incomplete_training_population",
                "Selected cases or budget-truncated rows may lack observations",
            )
        )
    model = DataPetriNet(net, data.features, tuple(points))
    value = DataPetriNetMining(
        model, tuple(sorted(selected)), fitted_rows, excluded_rows, tuple(tree_ids)
    )
    return _result(
        operator,
        table.source_digest,
        request,
        value,
        tuple(issues),
        parents + tuple(tree_ids),
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
    )


@dataclass(frozen=True, slots=True)
class DecisionFeatureValue:
    name: str
    value: int | float | None

    def __post_init__(self):
        _text(self.name, "feature name")
        if self.value is not None and not _numeric(self.value):
            raise ValueError("guard features must be finite numeric values or None")


@dataclass(frozen=True, slots=True)
class DataGuardEvaluationRequest:
    model_digest: str
    transition_id: str
    marking: Marking
    values: tuple[DecisionFeatureValue, ...]
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DecisionGuardResult:
    place_id: str
    state: Literal["true", "false", "unknown"]
    clause_states: tuple[str, ...]
    missing_features: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataGuardEvaluation:
    transition_id: str
    structurally_enabled: bool
    guard_state: Literal["true", "false", "unknown"]
    enabled: bool | None
    decisions: tuple[DecisionGuardResult, ...]


def _conjunction(states):
    return (
        "false" if "false" in states else "unknown" if "unknown" in states else "true"
    )


def _disjunction(states):
    return "true" if "true" in states else "unknown" if "unknown" in states else "false"


def evaluate_data_guards(
    model: DataPetriNet,
    marking: Marking,
    transition_id: str,
    values: tuple[DecisionFeatureValue, ...] = (),
) -> ComputationResult[DataGuardEvaluation]:
    """Three-valued guard evaluation plus the ordinary token enabling test."""
    if not isinstance(model, DataPetriNet) or not isinstance(marking, Marking):
        raise TypeError("expected DataPetriNet and Marking")
    if not isinstance(values, tuple) or not all(
        isinstance(item, DecisionFeatureValue) for item in values
    ):
        raise TypeError("values must be a tuple of DecisionFeatureValue")
    if len({item.name for item in values}) != len(values) or not {
        item.name for item in values
    }.issubset(feature.name for feature in model.features):
        raise ValueError("guard feature names must be unique and declared by the model")
    values = tuple(sorted(values, key=lambda item: item.name))
    source = data_petri_net_digest(model)
    request = DataGuardEvaluationRequest(source, transition_id, marking, values)
    structural = is_enabled(model.base, marking, transition_id)
    mapping = {item.name: item.value for item in values}
    results = []
    for point in model.decisions:
        if transition_id not in point.transition_ids:
            continue
        if point.status == "untrained":
            results.append(DecisionGuardResult(point.place_id, "unknown", (), ()))
            continue
        guard = next(
            guard for guard in point.guards if guard.transition_id == transition_id
        )
        clauses, missing = [], set()
        for clause in guard.clauses:
            states = []
            for condition in clause.conditions:
                observed = mapping.get(condition.feature_name)
                if observed is None:
                    missing.add(condition.feature_name)
                    states.append("unknown")
                else:
                    truth = (
                        observed <= condition.threshold
                        if condition.operator == "<="
                        else observed > condition.threshold
                    )
                    states.append("true" if truth else "false")
            clauses.append(_conjunction(states))
        results.append(
            DecisionGuardResult(
                point.place_id,
                _disjunction(clauses),
                tuple(clauses),
                tuple(sorted(missing)),
            )
        )
    state = _conjunction(tuple(result.state for result in results))
    enabled = (
        False
        if not structural or state == "false"
        else None
        if state == "unknown"
        else True
    )
    value = DataGuardEvaluation(
        transition_id, structural, state, enabled, tuple(results)
    )
    return _result("pix.case_centric.evaluate_data_guards", source, request, value)


def fire_data_transition(
    model: DataPetriNet,
    marking: Marking,
    transition_id: str,
    values: tuple[DecisionFeatureValue, ...] = (),
) -> Marking:
    """Pure guarded firing; unknown predicates cannot authorize a transition."""
    result = evaluate_data_guards(model, marking, transition_id, values)
    if result.value.enabled is not True:
        raise ValueError(f"data transition is not enabled: {result.value.guard_state}")
    return fire(model.base, marking, transition_id)


RESULT_SCHEMAS = {
    "pix.case_centric.extract_decision_table": (
        "case_decision_table",
        DecisionTableRequest,
        DecisionTable,
    ),
    "pix.case_centric.mine_data_petri_net": (
        "case_data_petri_net_mining",
        DataPetriNetMiningRequest,
        DataPetriNetMining,
    ),
    "pix.case_centric.evaluate_data_guards": (
        "case_data_guard_evaluation",
        DataGuardEvaluationRequest,
        DataGuardEvaluation,
    ),
}

__all__ = (
    "DecisionFeatureSpec",
    "DecisionTableSpec",
    "DecisionTableRequest",
    "DecisionPoint",
    "ObservedDecisionFeature",
    "DecisionObservation",
    "DecisionCaseExclusion",
    "DecisionTable",
    "discover_decision_points",
    "extract_decision_table",
    "DataGuardClause",
    "TransitionDataGuard",
    "DecisionPointModel",
    "DataPetriNet",
    "data_petri_net_digest",
    "DataPetriNetMiningSpec",
    "DataPetriNetMiningRequest",
    "DataPetriNetMining",
    "mine_data_petri_net",
    "DecisionFeatureValue",
    "DataGuardEvaluationRequest",
    "DecisionGuardResult",
    "DataGuardEvaluation",
    "evaluate_data_guards",
    "fire_data_transition",
)
