"""Native occurrence-weighted enabled-prefix precision with finite evidence.

All synchronous branches and all silent-reachable markings are retained for
each activity prefix. This measures enabled behavior, including dead ends,
without claiming accepting-language or ETConformance metric equivalence.
"""

from __future__ import annotations

from collections import deque

from pix.compute._common import _result
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import TraceSet
from pix.contracts.models import Marking, PetriNet
from pix.contracts.precision import (
    PrefixPrecision,
    PrefixPrecisionCoverage,
    PrefixPrecisionEvidence,
    PrefixPrecisionRequest,
    PrefixPrecisionSpec,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

PREFIX_PRECISION_OPERATOR_ID = "pix.prefix_precision"
Prefix = tuple[str, ...]


def _closure(
    net: PetriNet, seeds: set[Marking], cap: int, activities: dict[str, str | None]
) -> tuple[tuple[Marking, ...] | None, int]:
    """Return the complete epsilon closure or explicit incompleteness.

    The bound counts distinct admitted markings, including initial seeds.
    A cap hit only means incomplete when one additional marking is discovered;
    a complete closure containing exactly cap markings remains exact.
    """
    if len(seeds) > cap:
        return None, cap
    seen = set(seeds)
    pending = deque(sorted(seeds, key=lambda item: item.tokens))
    while pending:
        marking = pending.popleft()
        for transition_id in enabled_transitions(net, marking):
            if activities[transition_id] is not None:
                continue
            after = fire(net, marking, transition_id)
            if after in seen:
                continue
            if len(seen) >= cap:
                return None, len(seen)
            seen.add(after)
            pending.append(after)
    return tuple(sorted(seen, key=lambda item: item.tokens)), len(seen)


def _measure(
    traces: TraceSet, net: PetriNet, spec: PrefixPrecisionSpec, source_id: str
) -> tuple[PrefixPrecision, tuple[ComputeIssue, ...], bool]:
    visits: dict[Prefix, list[str]] = {}
    completed: dict[Prefix, list[str]] = {}
    observed: dict[Prefix, set[str]] = {}
    event_count = 0
    for trace in traces.traces:
        activities = tuple(event.activity for event in trace.events)
        event_count += len(activities)
        for position in range(len(activities) + 1):
            prefix = activities[:position]
            visits.setdefault(prefix, []).append(trace.object_id)
            observed.setdefault(prefix, set())
            if position < len(activities):
                observed[prefix].add(activities[position])
            else:
                completed.setdefault(prefix, []).append(trace.object_id)

    include_terminal = spec.terminal_policy == "include"
    activities = {transition.id: transition.activity for transition in net.transitions}
    closures: dict[Prefix, tuple[Marking, ...] | None] = {}
    evidence: list[PrefixPrecisionEvidence] = []
    issues: list[ComputeIssue] = []
    for prefix in sorted(visits, key=lambda item: (len(item), item)):
        object_ids = tuple(sorted(visits[prefix]))
        completed_ids = tuple(sorted(completed.get(prefix, ())))
        visit_count = len(object_ids)
        extension_count = visit_count - len(completed_ids)
        weight = visit_count if include_terminal else extension_count
        observed_labels = tuple(sorted(observed[prefix]))
        observed_termination = bool(completed_ids) if include_terminal else False
        status = "computed"
        closure: tuple[Marking, ...] | None = None
        explored = 0
        if not weight:
            status = "excluded_terminal_policy"
        elif prefix and closures[prefix[:-1]] is None:
            status = "upstream_search_limit"
        else:
            seeds: set[Marking] = set()
            if not prefix:
                seeds.add(net.initial_marking)
            else:
                parent = closures[prefix[:-1]]
                assert parent is not None
                for marking in parent:
                    for transition_id in enabled_transitions(net, marking):
                        if activities[transition_id] == prefix[-1]:
                            seeds.add(fire(net, marking, transition_id))
                            if len(seeds) > spec.max_markings_per_prefix:
                                break
                    if len(seeds) > spec.max_markings_per_prefix:
                        break
            closure, explored = _closure(
                net, seeds, spec.max_markings_per_prefix, activities
            )
            if closure is None:
                status = "search_limit"
            elif not closure:
                status = "unfit_prefix"
        closures[prefix] = closure
        enabled_labels = enabled_termination = None
        escaping_labels = escaping_termination = None
        missing_labels = missing_termination = None
        enabled_count = escaping_count = numerator = denominator = None
        if closure is not None:
            enabled_labels = tuple(
                sorted(
                    {
                        activities[transition_id]
                        for marking in closure
                        for transition_id in enabled_transitions(net, marking)
                        if activities[transition_id] is not None
                    }
                )
            )
            enabled_termination = (
                net.final_marking in closure if include_terminal else False
            )
            escaping_labels = tuple(sorted(set(enabled_labels) - set(observed_labels)))
            escaping_termination = enabled_termination and not observed_termination
            missing_labels = tuple(sorted(set(observed_labels) - set(enabled_labels)))
            missing_termination = observed_termination and not enabled_termination
            enabled_count = len(enabled_labels) + int(enabled_termination)
            escaping_count = len(escaping_labels) + int(escaping_termination)
            if status == "computed" and (missing_labels or missing_termination):
                status = "unfit_observation"
            if status == "computed":
                denominator = weight * enabled_count
                numerator = weight * (enabled_count - escaping_count)
        if status in ("unfit_prefix", "unfit_observation"):
            issues.append(
                ComputeIssue(
                    "precision_unfit_prefix",
                    "Prefix or observed continuation cannot replay synchronously; "
                    "its weight is excluded from the completed-prefix score",
                    ("prefix",) + prefix,
                )
            )
        elif status in ("search_limit", "upstream_search_limit"):
            issues.append(
                ComputeIssue(
                    "precision_search_limit",
                    "All reachable markings are unknown within the closure bound; "
                    "this prefix is excluded from the completed-prefix score",
                    ("prefix",) + prefix,
                )
            )
        evidence.append(
            PrefixPrecisionEvidence(
                prefix,
                object_ids,
                completed_ids,
                visit_count,
                extension_count,
                len(completed_ids),
                weight,
                observed_labels,
                observed_termination,
                status,
                None
                if closure is None
                else tuple(marking.tokens for marking in closure),
                explored,
                enabled_labels,
                enabled_termination,
                escaping_labels,
                escaping_termination,
                missing_labels,
                missing_termination,
                enabled_count,
                escaping_count,
                numerator,
                denominator,
            )
        )

    computed = [item for item in evidence if item.status == "computed"]
    unfit = [
        item
        for item in evidence
        if item.status in ("unfit_prefix", "unfit_observation")
    ]
    limited = [
        item
        for item in evidence
        if item.status in ("search_limit", "upstream_search_limit")
    ]
    coverage = PrefixPrecisionCoverage(
        len(traces.traces),
        sum(not trace.events for trace in traces.traces),
        event_count,
        sum(item.weight > 0 for item in evidence),
        len(computed),
        len(unfit),
        len(limited),
        sum(item.status == "excluded_terminal_policy" for item in evidence),
        sum(item.weight for item in evidence),
        sum(item.weight for item in computed),
        sum(item.weight for item in unfit),
        sum(item.weight for item in limited),
    )
    numerator = sum(item.weighted_retained_options or 0 for item in computed)
    denominator = sum(item.weighted_enabled_options or 0 for item in computed)
    incomplete = bool(unfit or limited)
    ratio = (numerator, denominator) if denominator and event_count else None
    metric_status = (
        "unavailable" if ratio is None else "partial" if incomplete else "computed"
    )
    if not event_count:
        issues.append(
            ComputeIssue(
                "precision_empty_event_population",
                "Precision is unavailable without an observed event occurrence",
            )
        )
    elif not denominator:
        issues.append(
            ComputeIssue(
                "precision_zero_denominator",
                "No computed prefix supplies an enabled-option denominator",
            )
        )
    return (
        PrefixPrecision(
            traces.object_type,
            model_digest(net),
            source_id,
            spec.terminal_policy,
            spec.weighting,
            tuple(evidence),
            coverage,
            metric_status,
            numerator,
            denominator,
            ratio,
            ratio if not incomplete else None,
        ),
        tuple(issues),
        incomplete,
    )


def measure_prefix_precision(
    traces: ComputationResult[TraceSet], net: PetriNet, spec: PrefixPrecisionSpec
) -> ComputationResult[PrefixPrecision]:
    """Measure PIX enabled-prefix precision under an explicit completion policy.

    A complete evidence calculation can contain an unavailable metric (empty
    event population or zero denominator), exposed by ``metric_status`` and
    null ratios. Incomplete prefix coverage instead marks the result PARTIAL.
    Whole-log precision is never filled using only a computed subset.
    """
    if not isinstance(traces, ComputationResult):
        raise TypeError("traces must be a ComputationResult[TraceSet]")
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
    if not isinstance(spec, PrefixPrecisionSpec):
        raise TypeError("spec must be PrefixPrecisionSpec")
    request = PrefixPrecisionRequest(model_digest(net), spec)
    parents = (traces.computation_id,) if traces.computation_id is not None else ()
    if traces.status is not ComputeStatus.COMPUTED or not isinstance(
        traces.value, TraceSet
    ):
        return _result(
            PREFIX_PRECISION_OPERATOR_ID,
            None,
            request,
            ComputeStatus.INVALID_INPUT
            if traces.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "trace_result_unavailable", "A completed TraceSet is required"
                ),
            )
            + traces.issues,
            source_digest=traces.source_digest,
            parent_computation_ids=parents,
        )
    assert traces.computation_id is not None
    value, issues, incomplete = _measure(traces.value, net, spec, traces.computation_id)
    return _result(
        PREFIX_PRECISION_OPERATOR_ID,
        None,
        request,
        ComputeStatus.PARTIAL if incomplete else ComputeStatus.COMPUTED,
        value,
        traces.issues + issues,
        source_digest=traces.source_digest,
        parent_computation_ids=parents,
    )


__all__ = ("PREFIX_PRECISION_OPERATOR_ID", "measure_prefix_precision")
