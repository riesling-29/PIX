"""Certified structural conversion of ordinary workflow nets to process trees.

Sequence, choice, isolated fork/join and enclosed do/redo fragments are
contracted to annotated transitions. This is a deliberately bounded structural
profile, not a converter for arbitrary P/T nets. A candidate is released only
after complete finite marking graphs and epsilon-NFA language comparison prove
equality of accepted visible traces. Infinite trace languages are supported
when their marking graphs are finite. This certificate does not claim branching
bisimulation, transition-identity, timing, token-statistic or probability
preservation. Weighted arcs are refused, never silently changed to unit arcs.

The reference is the operator-reduction family in PM4Py 2.7.23.8
objects/conversion/wf_net/variants/to_process_tree.py. This implementation uses
native immutable trees and explicit incidence checks; it does not serialize
labels into an expression or execute the reference package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pix.case_centric.model_analysis import (
    ModelComparison,
    ModelComparisonSpec,
    ReachabilitySpec,
    compare_models,
)
from pix.compute._common import _derived_result
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.model_semantics import model_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.case_centric.wfnet_to_process_tree"
PROFILE = "pix.wfnet.structural_language_certified.v1"


@dataclass(frozen=True, slots=True)
class WfNetConversionSpec:
    max_reductions: int = 10_000
    max_states: int = 10_000
    max_tokens: int = 1000
    max_comparison_states: int = 100_000
    max_tree_depth: int = 128
    max_pattern_checks: int = 1_000_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.WfNetConversionSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in (
            "max_reductions",
            "max_states",
            "max_tokens",
            "max_comparison_states",
            "max_tree_depth",
            "max_pattern_checks",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_tree_depth > 128:
            raise ValueError("max_tree_depth cannot exceed native conversion depth 128")


@dataclass(frozen=True, slots=True)
class WfNetConversionRequest:
    model_digest: str | None
    parameters: WfNetConversionSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.WfNetConversionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class WfNetReduction:
    rule: str
    transition_ids: tuple[str, ...]
    original_transition_ids: tuple[str, ...]
    removed_place_ids: tuple[str, ...]
    replacement_transition_id: str
    input_place_ids: tuple[str, ...]
    output_place_ids: tuple[str, ...]
    tree: ProcessTree


@dataclass(frozen=True, slots=True)
class WfNetLanguageCertificate:
    source_model_digest: str
    converted_model_digest: str
    comparison_computation_id: str
    comparison: ModelComparison


@dataclass(frozen=True, slots=True)
class WfNetConversion:
    model: ProcessTree | None
    profile: str
    source_model_digest: str
    reductions: tuple[WfNetReduction, ...]
    certificate: WfNetLanguageCertificate | None
    complete: bool
    remaining_place_ids: tuple[str, ...]
    remaining_transition_ids: tuple[str, ...]
    pattern_checks: int


class _Limit(Exception):
    pass


def _compose(operator, children):
    # Flatten associative operators only. Duplicate leaves and silent leaves
    # remain explicit, and a loop always retains its ordered do/redo children.
    flattened = []
    for child in children:
        if operator in ("sequence", "xor", "parallel") and child.operator == operator:
            flattened.extend(child.children)
        else:
            flattened.append(child)
    return (
        flattened[0]
        if len(flattened) == 1
        else ProcessTree(operator, children=tuple(flattened))
    )


def _workflow_boundaries(net):
    nodes = {p.id for p in net.places} | {t.id for t in net.transitions}
    incoming, outgoing = {n: set() for n in nodes}, {n: set() for n in nodes}
    for arc in net.arcs:
        incoming[arc.target].add(arc.source)
        outgoing[arc.source].add(arc.target)
    sources = [p.id for p in net.places if not incoming[p.id]]
    sinks = [p.id for p in net.places if not outgoing[p.id]]
    if len(sources) != 1 or len(sinks) != 1 or sources == sinks:
        return None
    source, sink = sources[0], sinks[0]
    if net.initial_marking != Marking(((source, 1),)) or net.final_marking != Marking(
        ((sink, 1),)
    ):
        return None

    def closure(start, graph):
        found, pending = {start}, [start]
        while pending:
            for target in graph[pending.pop()]:
                if target not in found:
                    found.add(target)
                    pending.append(target)
        return found

    if closure(source, outgoing) != nodes or closure(sink, incoming) != nodes:
        return None
    return source, sink


def wfnet_to_process_tree(
    net: PetriNet | ComputationResult,
    spec: WfNetConversionSpec = WfNetConversionSpec(),
) -> ComputationResult[WfNetConversion]:
    """Return a certified tree, or explicit unsupported/unknown evidence.

    Unsupported structure returns UNAVAILABLE with no tree; exhausting any
    search bound returns PARTIAL with no tree and never a negative equivalence
    claim. A computed parent can directly contain a net or expose ``.model``.
    Its source provenance is retained, while request identity includes the net.
    """
    if not isinstance(spec, WfNetConversionSpec):
        raise TypeError("spec must be WfNetConversionSpec")
    parent = net if isinstance(net, ComputationResult) else None
    inherited = parent.issues if parent is not None else ()
    parents = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    source = parent.source_digest if parent is not None else None
    digest = None

    def result(status, value=None, issues=()):
        return _derived_result(
            OPERATOR_ID,
            source,
            WfNetConversionRequest(digest, spec),
            status,
            value,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent is not None:
        if parent.status is not ComputeStatus.COMPUTED or parent.value is None:
            return result(
                ComputeStatus.UNAVAILABLE,
                issues=(
                    ComputeIssue(
                        "wfnet_input_unavailable", "A computed model result is required"
                    ),
                ),
            )
        net = (
            parent.value
            if isinstance(parent.value, PetriNet)
            else getattr(parent.value, "model", None)
        )
    if not isinstance(net, PetriNet):
        if parent is None:
            raise TypeError(
                "net must be PetriNet or ComputationResult containing a PetriNet"
            )
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_wfnet_payload",
                    "Result payload does not contain a PetriNet",
                ),
            ),
        )
    digest = model_digest(net)
    if parent is None:
        source = digest
    places = {p.id for p in net.places}
    trees = {
        t.id: ProcessTree("tau")
        if t.activity is None
        else ProcessTree("activity", t.activity)
        for t in net.transitions
    }
    origins = {t.id: (t.id,) for t in net.transitions}
    allocated_ids = places | set(trees)
    pre, post = {t: set() for t in trees}, {t: set() for t in trees}
    for arc in net.arcs:
        if arc.target in trees:
            pre[arc.target].add(arc.source)
        else:
            post[arc.source].add(arc.target)
    reductions, checks = [], 0

    def payload(tree=None, certificate=None, complete=False):
        return WfNetConversion(
            tree,
            PROFILE,
            digest,
            tuple(reductions),
            certificate,
            complete,
            tuple(sorted(places)),
            tuple(sorted(trees)),
            checks,
        )

    if any(arc.weight != 1 for arc in net.arcs):
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "weighted_wfnet_unsupported",
                    "This structural profile requires unit arcs; multiplicities were not changed",
                ),
            ),
        )
    boundaries = _workflow_boundaries(net)
    if boundaries is None:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "workflow_structure_unsupported",
                    "A single-source/sink workflow graph with all nodes on a source-to-sink path and exact singleton initial/final markings is required",
                ),
            ),
        )
    source_place, sink_place = boundaries

    def tick():
        nonlocal checks
        if checks >= spec.max_pattern_checks:
            raise _Limit("Structural pattern search reached max_pattern_checks")
        checks += 1

    def replace(rule, members, removed, inputs, outputs, tree):
        if len(reductions) >= spec.max_reductions:
            raise _Limit("Structural reduction reached max_reductions")
        pending = [(tree, 0)]
        while pending:
            node, depth = pending.pop()
            if depth > spec.max_tree_depth:
                raise _Limit("Candidate tree exceeds max_tree_depth")
            pending.extend((child, depth + 1) for child in node.children)
        identity = f"pix:wfnet:reduction:{len(reductions)}"
        # Input identifiers are arbitrary user data, including our prefix.
        while identity in allocated_ids:
            identity += ":new"
        allocated_ids.add(identity)
        original_ids = tuple(sorted(x for member in members for x in origins[member]))
        reductions.append(
            WfNetReduction(
                rule,
                tuple(members),
                original_ids,
                tuple(sorted(removed)),
                identity,
                tuple(sorted(inputs)),
                tuple(sorted(outputs)),
                tree,
            )
        )
        for member in members:
            del trees[member], pre[member], post[member], origins[member]
        places.difference_update(removed)
        trees[identity], pre[identity], post[identity], origins[identity] = (
            tree,
            set(inputs),
            set(outputs),
            original_ids,
        )

    def reduce_once():
        pin, pout = {p: set() for p in places}, {p: set() for p in places}
        for transition in trees:
            for p in pre[transition]:
                pout[p].add(transition)
            for p in post[transition]:
                pin[p].add(transition)
        ordered = sorted(trees)
        # A choice shares its entire consumption and production interface.
        groups = {}
        for transition in ordered:
            tick()
            key = (tuple(sorted(pre[transition])), tuple(sorted(post[transition])))
            groups.setdefault(key, []).append(transition)
        for (inputs, outputs), members in groups.items():
            if (
                len(members) >= 2
                and inputs
                and outputs
                and not set(inputs) & set(outputs)
            ):
                replace(
                    "xor",
                    members,
                    (),
                    inputs,
                    outputs,
                    _compose("xor", [trees[t] for t in members]),
                )
                return True
        # Enclosed binary do/redo loop: only the body leaves entry, only the
        # body enters exit. External edges can enter entry or leave exit.
        for body in ordered:
            tick()
            if len(pre[body]) != 1 or len(post[body]) != 1:
                continue
            entry, exit_ = next(iter(pre[body])), next(iter(post[body]))
            if entry == exit_ or {entry, exit_} & {source_place, sink_place}:
                continue
            if pout[entry] != {body} or pin[exit_] != {body}:
                continue
            for redo in sorted(pout[exit_] & pin[entry]):
                tick()
                if (
                    pre[redo] == {exit_}
                    and post[redo] == {entry}
                    and pin[entry] - {redo}
                    and pout[exit_] - {redo}
                ):
                    replace(
                        "loop",
                        (body, redo),
                        (),
                        {entry},
                        {exit_},
                        ProcessTree("loop", children=(trees[body], trees[redo])),
                    )
                    return True
        # An isolated single-entry/single-exit fork/join. Every branch has
        # already become one annotated transition; no external branch arcs.
        for split in ordered:
            tick()
            entries = post[split]
            if len(entries) < 2:
                continue
            branches, exits, join = [], set(), None
            valid = True
            for entry in sorted(entries):
                tick()
                if pin[entry] != {split} or len(pout[entry]) != 1:
                    valid = False
                    break
                branch = next(iter(pout[entry]))
                if branch == split or pre[branch] != {entry} or len(post[branch]) != 1:
                    valid = False
                    break
                exit_ = next(iter(post[branch]))
                if (
                    exit_ in entries
                    or exit_ in exits
                    or pin[exit_] != {branch}
                    or len(pout[exit_]) != 1
                ):
                    valid = False
                    break
                candidate_join = next(iter(pout[exit_]))
                if candidate_join == split or (
                    join is not None and join != candidate_join
                ):
                    valid = False
                    break
                branches.append(branch)
                exits.add(exit_)
                join = candidate_join
            if (
                not valid
                or join in branches
                or pre[join] != exits
                or (entries | exits) & {source_place, sink_place}
            ):
                continue
            members = (split, *branches, join)
            tree = _compose(
                "sequence",
                (
                    trees[split],
                    _compose("parallel", [trees[t] for t in branches]),
                    trees[join],
                ),
            )
            replace("parallel", members, entries | exits, pre[split], post[join], tree)
            return True
        # Contract a private intermediate place. Shared places and overlapping
        # interfaces are not sequence fragments in this conservative profile.
        for middle in sorted(places - {source_place, sink_place}):
            tick()
            if len(pin[middle]) != 1 or len(pout[middle]) != 1:
                continue
            first, second = next(iter(pin[middle])), next(iter(pout[middle]))
            if (
                first == second
                or post[first] != {middle}
                or pre[second] != {middle}
                or pre[first] & post[second]
            ):
                continue
            replace(
                "sequence",
                (first, second),
                {middle},
                pre[first],
                post[second],
                _compose("sequence", (trees[first], trees[second])),
            )
            return True
        return False

    try:
        while reduce_once():
            pass
    except _Limit as error:
        return result(
            ComputeStatus.PARTIAL,
            payload(),
            (ComputeIssue("wfnet_reduction_limit", str(error)),),
        )
    if len(trees) != 1 or places != {source_place, sink_place}:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "wfnet_irreducible",
                    "No supported structural reduction remains; irreducibility in this profile is not a proof that no equivalent process tree exists",
                ),
            ),
        )
    transition = next(iter(trees))
    if pre[transition] != {source_place} or post[transition] != {sink_place}:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "wfnet_residual_interface",
                    "The remaining fragment is not a single source-to-sink transition",
                ),
            ),
        )
    candidate = trees[transition]
    converted = process_tree_to_petri_net(candidate)
    comparison = compare_models(
        net,
        converted,
        ModelComparisonSpec(
            reachability=ReachabilitySpec(spec.max_states, spec.max_tokens),
            max_product_states=spec.max_comparison_states,
        ),
    )
    certificate = WfNetLanguageCertificate(
        digest, model_digest(converted), comparison.computation_id, comparison.value
    )
    parents += (comparison.computation_id,)
    if comparison.value.equivalent is None:
        return result(
            ComputeStatus.PARTIAL,
            payload(certificate=certificate),
            comparison.issues
            + (
                ComputeIssue(
                    "wfnet_certificate_unknown",
                    "A candidate exists, but exact language verification did not finish; no tree was released",
                ),
            ),
        )
    if comparison.value.equivalent is False:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "wfnet_certificate_counterexample",
                    "Structural candidate failed accepted-language equality; issue location records the distinguishing visible trace",
                    comparison.value.distinguishing_trace or (),
                ),
            ),
        )
    return result(ComputeStatus.COMPUTED, payload(candidate, certificate, True))


RESULT_SCHEMAS = {
    OPERATOR_ID: ("wfnet_conversion", WfNetConversionRequest, WfNetConversion)
}

__all__ = (
    "WfNetConversionSpec",
    "WfNetConversionRequest",
    "WfNetReduction",
    "WfNetLanguageCertificate",
    "WfNetConversion",
    "wfnet_to_process_tree",
)
