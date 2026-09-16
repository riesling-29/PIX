"""Explicit witness decoration and three-valued footprint comparison.

No replay, discovery, alignment search or performance calculation runs here.
Counts aggregate supplied witness records. Model hashes bind topology, while
request/parent hashes bind the caller's declared source and selection; neither
is an independent verification against an absent original event log.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from pix.case_centric.discovery import FootprintModel
from pix.case_centric.model_discovery import ModelFootprints
from pix.compute.model_semantics import _binding_incidence, model_digest
from pix.contracts.conformance import AlignmentSet
from pix.contracts.models import Marking, ObjectCentricPetriNet, ObjectMarking, PetriNet
from pix.contracts.replay import ReplaySet
from pix.contracts.result import ComputationResult, ComputeStatus, computation_identity
from pix.models import ModelArtifact
from pix.object_centric.conformance import ObjectReplay, ObjectReplayRequest
from pix.object_centric.model_integration import EnhancedObjectCentricPetriNet
from pix.object_centric.performance import OCReplayPerformance
from pix.results import result_from_json, result_json_bytes
from pix.viewer.visual_contracts import (
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    VisualField,
    VisualMetric,
    VisualPanel,
)
from pix.viewer.visual_model_adapters import model_panels

_REPLAY_METRICS = (
    "firing_count",
    "inserted_tokens",
    "consumed_tokens",
    "produced_tokens",
)
_ALIGNMENT_METRICS = (
    "firing_count",
    "synchronous_count",
    "model_move_count",
    "silent_count",
)


def _fields(**values):
    return tuple(VisualField(key, value) for key, value in values.items())


def _checked(result):
    if not isinstance(result, ComputationResult):
        raise TypeError("annotations must be an explicit ComputationResult")
    # Reconstruct typed payloads, including their invariant guards, and check
    # registered operator/spec/payload correspondence and request identity.
    checked = result_from_json(result_json_bytes(result))
    if checked != result:
        raise ValueError("annotation result does not preserve its typed contract")
    return checked


def _coverage(result, **values):
    return TablePanel(
        "annotation_coverage",
        "Annotation provenance and coverage",
        ("property", "value"),
        tuple(
            (key, value)
            for key, value in dict(
                operator=result.operator_id,
                source_digest=result.source_digest,
                computation_id=result.computation_id,
                status=result.status.value,
                parent_count=len(result.parent_computation_ids),
                **values,
            ).items()
        ),
        description=(
            "Counts are sums over supplied witnesses, not new calculations or "
            "whole-log estimates. Source hashes are declarations checked for "
            "internal consistency; the original log is not supplied to this view."
        ),
    )


def _decorate(panels, metric, values, *, unit="count", known=True, details=None):
    output = []
    for panel in panels:
        if type(panel) is not GraphPanel:
            output.append(panel)
            continue
        nodes = []
        for node in panel.nodes:
            if node.kind not in ("transition", "silent"):
                nodes.append(node)
                continue
            extra = _fields(
                annotation_population="supplied_witnesses",
                annotation_whole_population_known=known,
            ) + (() if details is None else details.get(node.id, ()))
            nodes.append(
                replace(
                    node,
                    metrics=node.metrics
                    + (VisualMetric(metric, values.get(node.id), unit),),
                    details=node.details + extra,
                )
            )
        output.append(
            replace(
                panel,
                nodes=tuple(nodes),
                description=panel.description
                + "\nAnnotation: "
                + metric
                + ". Model arcs and markings retain their original semantics; "
                "metrics refer only to supplied transition witnesses.",
            )
        )
    return tuple(output)


def _transition(net, tid, activity, silent):
    by_id = {transition.id: transition for transition in net.transitions}
    if tid not in by_id:
        raise ValueError("annotation witness references an unknown transition ID")
    expected = by_id[tid].activity
    if silent != (expected is None) or activity != expected:
        raise ValueError("annotation transition ID/activity/silent kind disagree")


def _cc_replay(net, value, metric):
    counts = Counter({transition.id: 0 for transition in net.transitions})
    if value.trace_count != len(value.traces):
        raise ValueError("replay trace population disagrees with witnesses")
    completed = sum(trace.status == "completed" for trace in value.traces)
    if (value.completed_count, value.limited_count) != (
        completed,
        len(value.traces) - completed,
    ):
        raise ValueError("replay completion population disagrees with witnesses")
    for trace in value.traces:
        if not trace.steps or trace.steps[0].kind != "initial":
            raise ValueError("replay requires its initial marking witness")
        if trace.steps[0].produced_tokens != net.initial_marking.tokens:
            raise ValueError("replay initial marking differs from supplied model")
        previous = ()
        event_ids = []
        for index, step in enumerate(trace.steps):
            if (step.event_id is not None) != (
                step.kind in ("visible", "log_deviation")
            ):
                raise ValueError("replay event presence differs from step kind")
            if (step.activity is not None) != (
                step.kind in ("visible", "log_deviation")
            ):
                raise ValueError("replay activity presence differs from step kind")
            if step.event_id is not None:
                event_ids.append(step.event_id)
            if step.kind == "initial" and (
                index != 0 or step.consumed_tokens or step.inserted_tokens
            ):
                raise ValueError("replay initial witness is malformed")
            if step.kind == "finalize" and (
                index != len(trace.steps) - 1
                or trace.status != "completed"
                or step.produced_tokens
            ):
                raise ValueError("replay finalization witness is malformed")
            if step.kind == "log_deviation" and (
                step.inserted_tokens or step.consumed_tokens or step.produced_tokens
            ):
                raise ValueError("log deviation cannot consume or produce model tokens")
            for tokens in (
                step.marking_before,
                step.marking_after,
                step.inserted_tokens,
                step.consumed_tokens,
                step.produced_tokens,
            ):
                net.validate_marking(Marking(tokens))
            if step.marking_before != previous:
                raise ValueError("replay witness marking is discontinuous")
            before, inserted = (
                Counter(dict(step.marking_before)),
                Counter(dict(step.inserted_tokens)),
            )
            consumed, produced = (
                Counter(dict(step.consumed_tokens)),
                Counter(dict(step.produced_tokens)),
            )
            if consumed - (
                before + inserted
            ) or before + inserted - consumed + produced != Counter(
                dict(step.marking_after)
            ):
                raise ValueError("replay witness token accounting is inconsistent")
            previous = step.marking_after
            if step.kind not in ("visible", "silent"):
                if step.transition_id is not None:
                    raise ValueError("unfired replay step cannot name a transition")
                continue
            _transition(net, step.transition_id, step.activity, step.kind == "silent")
            expected_in = Counter(
                {
                    arc.source: arc.weight
                    for arc in net.arcs
                    if arc.target == step.transition_id
                }
            )
            expected_out = Counter(
                {
                    arc.target: arc.weight
                    for arc in net.arcs
                    if arc.source == step.transition_id
                }
            )
            if consumed != expected_in or produced != expected_out:
                raise ValueError("replay token witness differs from model incidence")
            counts[step.transition_id] += (
                1
                if metric == "firing_count"
                else sum(count for _, count in getattr(step, metric))
            )
        if trace.status == "completed" and (
            trace.steps[-1].kind != "finalize"
            or trace.steps[-1].consumed_tokens != net.final_marking.tokens
        ):
            raise ValueError("completed replay requires the model's finalization")
        if len(event_ids) != trace.processed_event_count or len(set(event_ids)) != len(
            event_ids
        ):
            raise ValueError("replay processed population differs from event witnesses")
        if (
            trace.processed_event_count > trace.event_count
            or trace.status == "completed"
            and trace.processed_event_count != trace.event_count
        ):
            raise ValueError("replay completion differs from event population")
        if (
            trace.final_marking != net.final_marking.tokens
            or trace.ending_marking != previous
        ):
            raise ValueError(
                "replay final/ending markings differ from supplied witnesses"
            )
    return counts, completed == value.trace_count and value.excluded_count == 0


def _cc_alignments(net, value, metric, parameters):
    counts = Counter({transition.id: 0 for transition in net.transitions})
    coverage = value.coverage
    actual = Counter(trace.status for trace in value.alignments)
    if (
        coverage.requested,
        coverage.optimal,
        coverage.unreachable,
        coverage.search_limit,
    ) != (
        len(value.alignments),
        actual["optimal"],
        actual["unreachable"],
        actual["search_limit"],
    ):
        raise ValueError("alignment coverage disagrees with supplied paths")
    for trace in value.alignments:
        if trace.status != "optimal" and trace.moves:
            raise ValueError("nonoptimal alignment cannot supply a completed path")
        previous = net.initial_marking.tokens
        observed = []
        for move in trace.moves:
            if (move.event_id is not None) != (move.kind in ("synchronous", "log")):
                raise ValueError("alignment event presence differs from move kind")
            for tokens in (move.before_marking, move.after_marking):
                net.validate_marking(Marking(tokens))
            if move.before_marking != previous:
                raise ValueError("alignment witness marking is discontinuous")
            previous = move.after_marking
            if move.event_id is not None:
                observed.append(move.event_id)
            expected_cost = getattr(
                parameters,
                {
                    "synchronous": "synchronous_move_cost",
                    "silent": "silent_move_cost",
                    "model": "model_move_cost",
                    "log": "log_move_cost",
                }[move.kind],
            )
            if move.cost != expected_cost:
                raise ValueError("alignment move cost differs from request profile")
            if move.kind == "log":
                if (
                    move.transition_id is not None
                    or move.before_marking != move.after_marking
                ):
                    raise ValueError("log move cannot fire a model transition")
                continue
            _transition(net, move.transition_id, move.activity, move.kind == "silent")
            consumed = Counter(
                {
                    arc.source: arc.weight
                    for arc in net.arcs
                    if arc.target == move.transition_id
                }
            )
            produced = Counter(
                {
                    arc.target: arc.weight
                    for arc in net.arcs
                    if arc.source == move.transition_id
                }
            )
            before = Counter(dict(move.before_marking))
            if consumed - before or before - consumed + produced != Counter(
                dict(move.after_marking)
            ):
                raise ValueError("alignment witness differs from model incidence")
            wanted = {
                "synchronous_count": "synchronous",
                "model_move_count": "model",
                "silent_count": "silent",
            }
            counts[move.transition_id] += int(
                metric == "firing_count" or move.kind == wanted[metric]
            )
        if trace.status == "optimal" and (
            tuple(observed) != trace.event_ids
            or previous != net.final_marking.tokens
            or trace.cost != sum(move.cost for move in trace.moves)
        ):
            raise ValueError("optimal alignment path population/terminal/cost mismatch")
    return counts, coverage.optimal == coverage.requested and coverage.excluded == 0


def _oc_replay(net, replay, parameters, metric):
    counts = Counter({transition.id: 0 for transition in net.transitions})
    if replay.scope.selected_objects != net.objects:
        raise ValueError("replay selected objects differ from model object universe")
    if any(
        kind not in parameters.object_types for _, kind in replay.scope.selected_objects
    ):
        raise ValueError("replay selection includes an unrequested object type")
    if any(place.object_type not in parameters.object_types for place in net.places):
        raise ValueError("model place type is outside replay object selection")
    events = {event.event_id: event for event in replay.scope.events}
    for event in events.values():
        if parameters.qualifiers is not None and any(
            qualifier not in parameters.qualifiers
            for _, _, qualifier in event.relations
        ):
            raise ValueError("replay selection includes an unrequested qualifier")
    if replay.steps[0].produced_tokens != net.initial_marking.tokens:
        raise ValueError("replay initial tokens differ from supplied model")
    for step in replay.steps:
        for tokens in (
            step.marking_before,
            step.marking_after,
            step.inserted_tokens,
            step.consumed_tokens,
            step.produced_tokens,
        ):
            net.validate_marking(ObjectMarking(tokens))
        if step.binding is None:
            continue
        tid = step.binding.transition_id
        activity = None if step.kind == "silent" else events[step.event_id].activity
        _transition(net, tid, activity, step.kind == "silent")
        if (
            step.kind == "visible"
            and tuple((kind, ids) for kind, ids in step.binding.objects if ids)
            != events[step.event_id].objects
        ):
            raise ValueError("replay binding differs from selected event participation")
        incidence = _binding_incidence(net, step.binding)
        if incidence is None or incidence != (
            Counter(step.consumed_tokens),
            Counter(step.produced_tokens),
        ):
            raise ValueError(
                "replay binding token witness differs from model incidence"
            )
        counts[tid] += 1 if metric == "firing_count" else len(getattr(step, metric))
    if (
        replay.status == "completed"
        and replay.steps[-1].consumed_tokens != net.final_marking.tokens
    ):
        raise ValueError("replay finalization differs from model final marking")
    return counts, replay.status == "completed"


def _performance_panels(panels, result, performance, metric, enhanced=None):
    parameters = (
        result.spec.parameters.performance if enhanced is not None else result.spec
    )
    if (
        performance.profile,
        performance.measurements.profile,
        performance.token_selection,
        performance.silent_policy,
        performance.measurements.object_type,
        tuple(summary.metric for summary in performance.measurements.summaries),
    ) != (
        parameters.profile,
        parameters.profile,
        parameters.token_selection,
        parameters.silent_policy,
        parameters.object_type,
        parameters.metrics,
    ):
        raise ValueError("performance profile/selection/policy differs from request")
    parts = metric.split(":")
    if len(parts) != 3 or parts[0] != "performance" or parts[2] != "mean":
        raise ValueError(
            "performance metric must be performance:<supplied metric>:mean"
        )
    name = parts[1]
    summaries = {
        summary.metric: summary for summary in performance.measurements.summaries
    }
    if name not in summaries:
        raise ValueError("requested performance metric is absent from supplied result")
    summary = summaries[name]
    samples = summary.samples
    if (
        tuple(sample.event_id for sample in samples)
        != performance.measurements.selected_event_ids
    ):
        raise ValueError("performance samples differ from selected event population")
    if (
        tuple(row.event_id for row in performance.token_inputs)
        != performance.measurements.selected_event_ids
    ):
        raise ValueError("performance token inputs differ from selected population")
    for item in performance.measurements.summaries:
        known = [sample.value for sample in item.samples if sample.value is not None]
        if (
            item.population_count,
            item.known_count,
            item.unknown_count,
            item.total,
        ) != (
            len(item.samples),
            len(known),
            len(item.samples) - len(known),
            sum(known),
        ):
            raise ValueError("performance aggregate disagrees with supplied samples")
        if any(
            sample.metric != item.metric or sample.unit != item.unit
            for sample in item.samples
        ):
            raise ValueError("performance metric/unit differs from sample evidence")
        if (item.mean_numerator, item.mean_denominator) != (
            (sum(known), len(known)) if known else (None, None)
        ):
            raise ValueError("performance mean differs from known sample population")
        if (item.minimum, item.maximum) != (
            (min(known), max(known)) if known else (None, None)
        ):
            raise ValueError("performance extrema differ from known sample population")
    assigned = {}
    if enhanced is not None:
        values, details = {}, {}
        for row in enhanced.transition_diagnostics:
            current = next(item for item in row.metrics if item.metric == name)
            values[row.transition_id] = (
                current.mean_numerator / current.mean_denominator
                if current.known_count
                else None
            )
            details[row.transition_id] = _fields(
                known_sample_count=current.known_count,
                unknown_sample_count=current.unknown_count,
                selected_sample_count=current.population_count,
                mean_numerator=current.mean_numerator,
                mean_denominator=current.mean_denominator,
            )
            assigned.update((eid, row.transition_id) for eid in row.observed_event_ids)
        panels = _decorate(
            panels,
            metric,
            values,
            unit=summary.unit,
            known=performance.replay_status == "completed"
            and summary.unknown_count == 0,
            details=details,
        )
    sample_panel = TablePanel(
        "annotation_samples",
        "Supplied timed-token samples",
        ("event_id", "transition_id", "metric", "value", "unit", "unknown_reason"),
        tuple(
            (
                sample.event_id,
                assigned.get(sample.event_id),
                name,
                sample.value,
                sample.unit,
                sample.reason,
            )
            for sample in samples
        ),
        description=(
            "Profile: "
            + performance.profile
            + ". Means use known samples only; exact numerator/denominator and unknown counts are retained. "
            + (
                "Transition IDs come from embedded replay witnesses."
                if enhanced is not None
                else "Transition assignment is unavailable: this payload has no event-to-transition witness. Graph nodes are not decorated."
            )
        ),
    )
    return panels + (
        sample_panel,
        _coverage(
            result,
            performance_profile=performance.profile,
            selected_event_count=len(performance.measurements.selected_event_ids),
            known_count=summary.known_count,
            unknown_count=summary.unknown_count,
            transition_assignment_available=enhanced is not None,
            selected_object_type=performance.measurements.object_type,
        ),
    )


def model_annotation_panels(
    model_or_artifact, result: ComputationResult, *, metric: str
) -> tuple[VisualPanel, ...]:
    """Bind explicit replay/alignment/OPERA evidence to its exact supplied net.

    Replay metrics: firing_count, inserted_tokens, consumed_tokens,
    produced_tokens. Alignment metrics: firing_count, synchronous_count,
    model_move_count, silent_count. Timed metrics: performance:<name>:mean.
    Only EnhancedObjectCentricPetriNet contains enough provenance to place
    timed samples on individual transitions; standalone timed replay gets an
    event table beside an unchanged graph. None never becomes a zero duration.
    """
    if type(metric) is not str or not metric:
        raise ValueError("an explicit annotation metric is required")
    net = (
        model_or_artifact.model
        if isinstance(model_or_artifact, ModelArtifact)
        else model_or_artifact
    )
    if type(net) not in (PetriNet, ObjectCentricPetriNet):
        raise TypeError(
            "model annotations require a native PetriNet or ObjectCentricPetriNet"
        )
    result = _checked(result)
    value = result.value
    identity = model_digest(net)
    if value is None:
        # Failed requests can still bind their intended model, but never carry
        # observed counts. Timed replay alone has no model in its request and
        # consequently cannot establish even this binding without its payload.
        allowed = {
            "pix.replay_traces": (PetriNet, _REPLAY_METRICS),
            "pix.align_traces": (PetriNet, _ALIGNMENT_METRICS),
            "pix.object_centric.token_replay": (ObjectCentricPetriNet, _REPLAY_METRICS),
        }
        expected = allowed.get(result.operator_id)
        if (
            expected is None
            or type(net) is not expected[0]
            or metric not in expected[1]
        ):
            raise ValueError(
                "unavailable annotation has no supported model/metric binding"
            )
        if getattr(result.spec, "model_digest", None) != identity:
            raise ValueError(
                "unavailable annotation request refers to a different model"
            )
        panels = _decorate(model_panels(net), metric, {}, known=False)
        return panels + (
            _coverage(
                result,
                metric=metric,
                witness_available=False,
                whole_population_known=False,
            ),
        )
    payload_digest = (
        model_digest(value.model)
        if isinstance(value, EnhancedObjectCentricPetriNet)
        else getattr(value, "model_digest", None)
    )
    if identity != payload_digest:
        raise ValueError("annotation model digest differs from supplied model")
    request_digest = getattr(result.spec, "model_digest", identity)
    if request_digest != identity:
        raise ValueError("annotation request model differs from supplied model")
    panels = model_panels(net)
    if isinstance(value, EnhancedObjectCentricPetriNet):
        if type(net) is not ObjectCentricPetriNet:
            raise TypeError("enhanced object annotations require an OCPN")
        parameters = result.spec.parameters
        if (
            value.performance.profile,
            value.performance.measurements.object_type,
            tuple(s.metric for s in value.performance.measurements.summaries),
        ) != (
            parameters.performance.profile,
            parameters.performance.object_type,
            parameters.performance.metrics,
        ):
            raise ValueError(
                "performance profile/selection differs from enhanced request"
            )
        selected = tuple(
            sorted(
                event.event_id
                for event in value.replay.scope.events
                if parameters.performance.activities is None
                or event.activity in parameters.performance.activities
            )
        )
        if value.performance.measurements.selected_event_ids != selected:
            raise ValueError(
                "performance selected events differ from requested activities"
            )
        _oc_replay(net, value.replay, parameters.replay, "firing_count")
        replay_id = computation_identity(
            "pix.object_centric.token_replay",
            result.operator_version,
            result.source_digest,
            # The inner request binds the exact original object selection.
            ObjectReplayRequest(identity, parameters.replay),
        )
        performance_id = computation_identity(
            "pix.object_centric.measure_replay_performance",
            result.operator_version,
            result.source_digest,
            parameters.performance,
            (replay_id,),
        )
        if result.parent_computation_ids != (replay_id, performance_id):
            raise ValueError(
                "enhanced annotation parent/source/selection identity mismatch"
            )
        if metric in _REPLAY_METRICS:
            counts, known = _oc_replay(net, value.replay, parameters.replay, metric)
        else:
            return _performance_panels(panels, result, value.performance, metric, value)
    elif isinstance(value, OCReplayPerformance):
        if (
            type(net) is not ObjectCentricPetriNet
            or len(result.parent_computation_ids) != 1
        ):
            raise ValueError(
                "timed object replay requires its model and one replay parent"
            )
        if (
            value.profile,
            value.measurements.object_type,
            tuple(s.metric for s in value.measurements.summaries),
        ) != (result.spec.profile, result.spec.object_type, result.spec.metrics):
            raise ValueError("performance profile/selection differs from request")
        return _performance_panels(panels, result, value, metric)
    elif isinstance(value, ReplaySet):
        if type(net) is not PetriNet or metric not in _REPLAY_METRICS:
            raise ValueError("unsupported Petri-net replay annotation metric")
        if len(result.parent_computation_ids) != 1:
            raise ValueError("case replay annotation requires its source trace parent")
        counts, known = _cc_replay(net, value, metric)
    elif isinstance(value, AlignmentSet):
        if type(net) is not PetriNet or metric not in _ALIGNMENT_METRICS:
            raise ValueError("unsupported Petri-net alignment annotation metric")
        counts, known = _cc_alignments(net, value, metric, result.spec.parameters)
    elif isinstance(value, ObjectReplay):
        if type(net) is not ObjectCentricPetriNet or metric not in _REPLAY_METRICS:
            raise ValueError("unsupported object-token replay annotation metric")
        counts, known = _oc_replay(net, value, result.spec.parameters, metric)
    else:
        raise TypeError("unsupported model annotation payload")
    return _decorate(panels, metric, counts, known=known) + (
        _coverage(
            result,
            metric=metric,
            whole_population_known=known,
            count_population="all supplied firing witnesses, including limited prefixes",
        ),
    )


def _footprint(value):
    envelope_complete = True
    if isinstance(value, ComputationResult):
        envelope_complete = value.status is ComputeStatus.COMPUTED
        value = _checked(value).value
    if type(value) not in (FootprintModel, ModelFootprints):
        raise TypeError("footprint comparison requires native log/model footprints")
    model_panels(value)  # Validate the supported model without calculating it.
    if isinstance(value, ModelFootprints):
        return (
            value,
            set(value.declared_activities),
            value.complete and envelope_complete,
            value.behavior,
        )
    return value, set(value.activities), envelope_complete, "observed_log_adjacency"


def _relation(model, alphabet, complete, a, b):
    if a not in alphabet or b not in alphabet:
        return "outside_alphabet", None, None
    follows = set(model.directly_follows)
    forward = True if (a, b) in follows else False if complete else None
    reverse = True if (b, a) in follows else False if complete else None
    if a == b:
        symbol = "self" if forward else "#" if forward is False else "?"
    else:
        symbol = {
            (True, True): "||",
            (True, False): "->",
            (False, True): "<-",
            (False, False): "#",
            (True, None): "follows?",
            (None, True): "precedes?",
        }.get((forward, reverse), "?")
    return symbol, forward, reverse


def footprint_comparison_panels(
    left, right, *, symmetric: bool = False
) -> tuple[MatrixPanel, ...]:
    """Compare adjacency over the union alphabet, preserving unknown relations.

    Differences compare observed/proven adjacency under each supplied profile;
    they do not compute footprint conformance or establish concurrency.
    Missing activities are outside that input's alphabet, never negative facts.
    By default every left adjacency must be supported by the right footprint;
    symmetric=True additionally checks right-to-left inclusion.
    """
    if type(symmetric) is not bool:
        raise TypeError("symmetric must be a boolean")
    lhs, lhs_alphabet, lhs_complete, lhs_profile = _footprint(left)
    rhs, rhs_alphabet, rhs_complete, rhs_profile = _footprint(right)
    activities = tuple(sorted(lhs_alphabet | rhs_alphabet))
    left_cells, right_cells, comparison = [], [], []
    legend = _fields(
        **{
            "->": "forward adjacency only",
            "<-": "reverse adjacency only",
            "||": "both adjacency directions, not proof of concurrency",
            "self": "self succession",
            "#": "absent under this completed profile",
            "?": "unknown under incomplete exploration",
            "follows?": "forward witnessed; reverse unknown",
            "precedes?": "reverse witnessed; forward unknown",
            "outside_alphabet": "activity absent from this input's alphabet",
        }
    )
    for a in activities:
        for b in activities:
            lv = _relation(lhs, lhs_alphabet, lhs_complete, a, b)
            rv = _relation(rhs, rhs_alphabet, rhs_complete, a, b)
            left_cells.append(
                MatrixCell(a, b, lv[0], details=_fields(forward=lv[1], reverse=lv[2]))
            )
            right_cells.append(
                MatrixCell(a, b, rv[0], details=_fields(forward=rv[1], reverse=rv[2]))
            )
            compared = tuple(zip(lv[1:], rv[1:]))
            mismatch = any(
                x is True and y is False or symmetric and x is False and y is True
                for x, y in compared
            )
            uncertain = any(
                x is None
                and (symmetric or y is not True)
                or y is None
                and (symmetric or x is not False)
                for x, y in compared
            )
            if mismatch:
                kind = (
                    "directional_mismatch"
                    if {lv[0], rv[0]} == {"->", "<-"}
                    else "symmetry_mismatch"
                    if "||" in (lv[0], rv[0])
                    else "relation_mismatch"
                )
                match = False
            elif "outside_alphabet" in (lv[0], rv[0]) or uncertain:
                kind, match = "unknown", None
            else:
                kind, match = ("equal" if symmetric else "supported"), True
            comparison.append(
                MatrixCell(
                    a,
                    b,
                    kind,
                    kind=kind,
                    details=_fields(left=lv[0], right=rv[0], match=match),
                )
            )
    description = (
        f"Left profile: {lhs_profile}; right profile: {rhs_profile}. "
        + (
            "Symmetric relation equality. "
            if symmetric
            else "Directional left-to-right adjacency inclusion. "
        )
        + "Comparison uses the union activity alphabet. Unknown/missing is distinct "
        "from a proven absent relation; this is not a conformance score."
    )
    return (
        MatrixPanel(
            "footprint_left",
            "Left footprint",
            activities,
            activities,
            tuple(left_cells),
            legend=legend,
            description=description,
        ),
        MatrixPanel(
            "footprint_right",
            "Right footprint",
            activities,
            activities,
            tuple(right_cells),
            legend=legend,
            description=description,
        ),
        MatrixPanel(
            "footprint_comparison",
            "Footprint relation comparison",
            activities,
            activities,
            tuple(comparison),
            legend=_fields(
                equal="Both adjacency directions agree under their supplied profiles",
                supported="Every left adjacency is supported by the right footprint",
                directional_mismatch="Opposite directed adjacency",
                symmetry_mismatch="Symmetric adjacency differs from the other relation",
                relation_mismatch="At least one known adjacency direction differs",
                unknown="Missing alphabet member or insufficient negative evidence",
            ),
            description=description,
        ),
    )


__all__ = ("model_annotation_panels", "footprint_comparison_panels")
