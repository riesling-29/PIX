"""Native model views that retain model structure instead of inferring a DFG.

The adapters describe supplied models. They do not discover behavior, establish
soundness, or convert observational evidence into execution probabilities.
Occurrence paths identify tree nodes; all supplied net and BPMN identifiers
remain available verbatim. JSON-valued detail cells are inert text, never HTML.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from itertools import combinations

from pix.case_centric.decision_mining import DataPetriNet
from pix.case_centric.declarative import DeclareModel, LogSkeleton, TemporalProfile
from pix.case_centric.discovery import FootprintModel, TransitionSystem
from pix.case_centric.heuristics import HeuristicsNet
from pix.case_centric.model_discovery import ModelFootprints
from pix.case_centric.powl import POWLNode
from pix.case_centric.split_miner import SplitBPMN
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import ObjectCentricPetriNet, PetriNet
from pix.models import model_from_json, model_json_bytes
from pix.object_centric.discovery import StochasticArcWeightNet
from pix.object_centric.models import ObjectCentricCausalNet
from pix.results import _decode, _encode

# Shared immutable contracts are imported below; no layout engine is required.
from pix.viewer.visual_contracts import (
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    VisualEdge,
    VisualField,
    VisualNode,
)

_SUPPORTED = (
    PetriNet,
    ObjectCentricPetriNet,
    ProcessTree,
    POWLNode,
    SplitBPMN,
    HeuristicsNet,
    TransitionSystem,
    FootprintModel,
    DeclareModel,
    LogSkeleton,
    TemporalProfile,
    DataPetriNet,
    ObjectCentricCausalNet,
    StochasticArcWeightNet,
)


def _json_value(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _text(value):
    value = _json_value(value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _details(**values):
    return tuple(VisualField(name, _text(value)) for name, value in values.items())


def _id(kind, *parts):
    """Length-unambiguous IDs, including labels containing delimiters."""
    return kind + ":" + json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def _node(identifier, label, kind="activity", **details):
    return VisualNode(
        identifier,
        label,
        kind=kind,
        group=details.get("object_type"),
        details=_details(**details),
    )


def _edge(identifier, source, target, label="", kind="relation", **details):
    return VisualEdge(
        identifier, source, target, label=label, kind=kind, details=_details(**details)
    )


def _graph(identifier, title, nodes, edges, *notes):
    return GraphPanel(
        identifier, title, tuple(nodes), tuple(edges), description="\n".join(notes)
    )


def _table(identifier, title, columns, rows, *notes):
    return TablePanel(
        identifier,
        title,
        tuple(columns),
        tuple(tuple(_text(cell) for cell in row) for row in rows),
        description="\n".join(
            (
                *notes,
                "Structured record, tuple and distribution cells contain JSON text.",
            )
        ),
    )


def _pn(model):
    oc = isinstance(model, ObjectCentricPetriNet)
    nodes, edges = [], []
    if oc:
        initial = {p.id: [] for p in model.places}
        final = {p.id: [] for p in model.places}
        for token in model.initial_marking.tokens:
            initial[token.place_id].append(token.object_id)
        for token in model.final_marking.tokens:
            final[token.place_id].append(token.object_id)
    else:
        initial, final = (
            dict(model.initial_marking.tokens),
            dict(model.final_marking.tokens),
        )
    place_types = {}
    for place in model.places:
        attrs = dict(
            model_id=place.id,
            initial_tokens=initial.get(place.id, 0),
            final_tokens=final.get(place.id, 0),
        )
        if oc:
            place_types[place.id] = place.object_type
            attrs.update(
                object_type=place.object_type,
                initial_count=len(initial[place.id]),
                final_count=len(final[place.id]),
            )
        else:
            attrs.update(
                initial_count=initial.get(place.id, 0),
                final_count=final.get(place.id, 0),
            )
        nodes.append(_node(place.id, place.id, "place", **attrs))
    for transition in model.transitions:
        nodes.append(
            _node(
                transition.id,
                "τ" if transition.activity is None else transition.activity,
                "silent" if transition.activity is None else "transition",
                model_id=transition.id,
                activity=transition.activity,
            )
        )
    for arc in model.arcs:
        if oc:
            upper = "∞" if arc.max_objects is None else str(arc.max_objects)
            label = f"{arc.min_objects}..{upper}" if arc.variable else "1"
            attrs = dict(
                object_type=place_types.get(arc.source, place_types.get(arc.target)),
                weight=1,
                variable=arc.variable,
                min_objects=arc.min_objects,
                max_objects=arc.max_objects,
            )
        else:
            label, attrs = str(arc.weight), dict(weight=arc.weight)
        edges.append(
            _edge(
                _id("incidence", arc.source, arc.target),
                arc.source,
                arc.target,
                label,
                "arc",
                **attrs,
            )
        )
    panels = [
        _graph(
            "model",
            "Object-centric Petri net" if oc else "Petri net",
            nodes,
            edges,
            "Token markings and incidence weights are model semantics, not observed event frequencies.",
            "Equal activity labels retain distinct transition identities; τ denotes a silent transition.",
        )
    ]
    if oc:
        panels.append(
            _table(
                "objects",
                "Declared object universe",
                ("object_id", "object_type"),
                model.objects,
                "Idle objects remain in the finite model universe. Repeated marking tokens retain multiplicity.",
                "All arcs of one transition and object type share one selected object set and cardinality policy.",
            )
        )
    return tuple(panels)


def _tree(model):
    powl = isinstance(model, POWLNode)
    nodes, edges = [], []
    pending = [(model, "root")]
    while pending:
        value, path = pending.pop()
        kind = value.kind if powl else value.operator
        label = value.activity if kind == "activity" else "τ" if kind == "tau" else kind
        nodes.append(
            _node(
                path,
                label,
                "activity"
                if kind == "activity"
                else "silent"
                if kind == "tau"
                else "operator",
                operator=kind,
                occurrence_path=path,
            )
        )
        for index, child in enumerate(value.children):
            child_id = f"{path}/{index}"
            role = ("do", "redo")[index] if kind == "loop" else str(index)
            edges.append(
                _edge(
                    _id("child", path, index),
                    path,
                    child_id,
                    role,
                    "contains",
                    child_index=index,
                    role=role,
                )
            )
            pending.append((child, child_id))
        order = (
            value.order
            if powl
            else tuple((i, i + 1) for i in range(len(value.children) - 1))
            if kind == "sequence"
            else ()
        )
        for left, right in order:
            edges.append(
                _edge(
                    _id("precedence", path, left, right),
                    f"{path}/{left}",
                    f"{path}/{right}",
                    "precedes",
                    "precedence",
                    scope=path,
                )
            )
    return (
        _graph(
            "model",
            "POWL" if powl else "Process tree",
            nodes,
            edges,
            "Containment edges describe syntax; they are not execution directly-follows edges.",
            "loop means do (redo do)*; XOR selects one child; parallel permits all child interleavings.",
            "POWL precedence requires the entire predecessor child to complete before the successor starts. Missing precedence permits interleaving.",
            "Occurrence paths preserve duplicate labels and child order without merging nodes.",
        ),
    )


def _bpmn(model):
    return (
        _graph(
            "model",
            "BPMN control flow",
            (
                _node(
                    n.id,
                    n.activity if n.activity is not None else n.kind.replace("_", " "),
                    n.kind,
                    model_id=n.id,
                    gateway_direction=n.direction,
                    start=n.id == model.start_id,
                    end=n.id == model.end_id,
                )
                for n in model.nodes
            ),
            (
                _edge(f.id, f.source, f.target, kind="sequence_flow", model_id=f.id)
                for f in model.flows
            ),
            "This model supports task/start/end and XOR/AND gateways with explicit split/join direction.",
            "Gateway nodes retain control semantics; no extra activity sequence is inferred.",
        ),
    )


def _transition_system(model):
    return (
        _graph(
            "model",
            "Transition system",
            (
                _node(
                    s.id,
                    json.dumps(s.context, ensure_ascii=False),
                    "state",
                    model_id=s.id,
                    context=s.context,
                    visits=s.visits,
                    initial_count=s.initial_count,
                    final_count=s.final_count,
                )
                for s in model.states
            ),
            (
                _edge(
                    _id("state_transition", e.source, e.target, e.activity),
                    e.source,
                    e.target,
                    e.activity,
                    "state_transition",
                    occurrence_count=e.occurrence_count,
                )
                for e in model.transitions
            ),
            f"Trace count: {model.trace_count}; complete exploration: {model.complete}.",
            "Context-state identities are preserved; multiple activities may connect the same states.",
        ),
    )


def _footprints(model):
    follows, causal, parallel = (
        set(model.directly_follows),
        set(model.causal),
        set(model.parallel),
    )
    rows = []
    for left in model.activities:
        for right in model.activities:
            symbol = (
                "self"
                if left == right and (left, right) in follows
                else "||"
                if (left, right) in parallel
                else "->"
                if (left, right) in causal
                else "<-"
                if (right, left) in causal
                else "#"
            )
            rows.append(
                MatrixCell(
                    left,
                    right,
                    symbol,
                    details=_details(directly_follows=(left, right) in follows),
                )
            )
    return (
        MatrixPanel(
            "footprints",
            "Activity footprints",
            model.activities,
            model.activities,
            tuple(rows),
            legend=_details(
                **{
                    "->": "asymmetric observed succession",
                    "<-": "reverse asymmetric observed succession",
                    "||": "observed bidirectional adjacency, not proven concurrency",
                    "#": "no observed adjacency",
                    "self": "observed self succession",
                }
            ),
            description="Cells describe observed adjacency relations, not executable model behavior.",
        ),
        _table(
            "boundaries",
            "Footprint boundaries",
            ("activity", "start", "end", "self_succession"),
            (
                (
                    a,
                    a in model.start_activities,
                    a in model.end_activities,
                    a in model.loop_activities,
                )
                for a in model.activities
            ),
            f"Minimum trace length: {model.minimum_trace_length}; empty trace count: {model.empty_trace_count}.",
        ),
    )


def _heuristics(model):
    ids = {a.activity: _id("activity", a.activity) for a in model.activities}
    nodes = [
        _node(
            ids[a.activity],
            a.activity,
            count=a.count,
            start_count=a.start_count,
            end_count=a.end_count,
        )
        for a in model.activities
    ]
    edges = [
        _edge(_id("selected", a, b), ids[a], ids[b], kind="selected_dependency")
        for a, b in model.edges
    ]
    for binding in model.bindings:
        for index, alternative in enumerate(binding.alternatives):
            group = _id("binding", binding.activity, binding.direction, index)
            nodes.append(
                _node(
                    group,
                    f"AND {index}",
                    "binding",
                    activity=binding.activity,
                    direction=binding.direction,
                    alternative_index=index,
                    members=alternative,
                )
            )
            source, target = (
                (group, ids[binding.activity])
                if binding.direction == "input"
                else (ids[binding.activity], group)
            )
            edges.append(
                _edge(
                    _id("binding_owner", group),
                    source,
                    target,
                    "alternative",
                    "binding",
                )
            )
            for member in alternative:
                source, target = (
                    (ids[member], group)
                    if binding.direction == "input"
                    else (group, ids[member])
                )
                edges.append(
                    _edge(
                        _id("binding_member", group, member),
                        source,
                        target,
                        "AND member",
                        "binding_member",
                    )
                )
    return (
        _graph(
            "model",
            "Heuristics net",
            nodes,
            edges,
            f"Profile: {model.profile}; traces: {model.trace_count}; empty traces: {model.empty_trace_count}.",
            "Each binding node is one AND alternative; alternatives for the same activity/direction are choices. Selected dependency edges alone do not express these groups.",
        ),
        _table(
            "dependencies",
            "Dependency evidence",
            (
                "source",
                "target",
                "count",
                "reverse_count",
                "overlap_count",
                "measure",
                "selected",
            ),
            (
                (
                    d.source,
                    d.target,
                    d.count,
                    d.reverse_count,
                    d.overlap_count,
                    d.measure,
                    d.selected,
                )
                for d in model.dependencies
            ),
        ),
        _table(
            "heuristics_evidence",
            "Frequency, loop and binding evidence",
            ("kind", "record"),
            (
                (kind, record)
                for kind, records in (
                    ("follows", model.follows),
                    ("overlaps", model.overlaps),
                    ("short_loop", model.short_loops),
                    ("and_pair", model.and_pairs),
                    ("binding", model.bindings),
                    ("excluded_activity", model.excluded_activities),
                    ("precleaned_edge", model.precleaned_edges),
                )
                for record in records
            ),
        ),
    )


def _validate_model_footprints(model):
    """Check supplied evidence consistency without executing the absent net."""
    checked = _decode(_encode(model), ModelFootprints)
    alphabet = set(model.declared_activities)
    if checked != model or len(alphabet) != len(model.declared_activities):
        raise ValueError("model footprint must preserve its typed, unique alphabet")
    if model.behavior not in ("reachable", "accepting") or model.model_kind not in (
        "petri-net",
        "process-tree",
    ):
        raise ValueError("unsupported model footprint profile")
    if (
        not model.model_digest.strip()
        or model.analysis_steps < 0
        or (model.minimum_trace_length is not None and model.minimum_trace_length < 0)
    ):
        raise ValueError("model footprint identity and counts must be valid")
    for name in (
        "declared_activities",
        "activities",
        "inactive_activities",
        "self_succession",
        "start_activities",
        "end_activities",
        "always_activities",
    ):
        values = getattr(model, name)
        if values is not None and (
            len(set(values)) != len(values)
            or any(not a.strip() or a not in alphabet for a in values)
        ):
            raise ValueError(f"{name} must contain unique declared activities")
    for pairs in (
        model.directly_follows,
        model.parallel,
        model.sequence or (),
        model.unrelated or (),
        model.commuting_pairs,
    ):
        if len(set(pairs)) != len(pairs) or any(
            a not in alphabet or b not in alphabet for a, b in pairs
        ):
            raise ValueError("model footprint refers to an undeclared activity")
    follows = set(model.directly_follows)
    if set(model.parallel) != {
        (a, b) for a, b in follows if a != b and (b, a) in follows
    }:
        raise ValueError("parallel relations disagree with witnessed adjacency")
    if set(model.self_succession) != {a for a, b in follows if a == b}:
        raise ValueError("self succession disagrees with witnessed adjacency")
    if model.complete:
        if not model.reachability.complete:
            raise ValueError("complete footprints require complete reachability")
        if model.sequence is None or set(model.sequence) != {
            (a, b) for a, b in follows if (b, a) not in follows
        }:
            raise ValueError("sequence relations disagree with completed adjacency")
        expected = {
            (a, b)
            for a, b in combinations(sorted(model.activities), 2)
            if (a, b) not in follows and (b, a) not in follows
        }
        if model.unrelated is None or set(model.unrelated) != expected:
            raise ValueError("unrelated relations disagree with completed adjacency")
        if model.inactive_activities is None or set(
            model.inactive_activities
        ) != alphabet - set(model.activities):
            raise ValueError("inactive activities disagree with completed exploration")
    elif any(
        v is not None
        for v in (model.sequence, model.unrelated, model.inactive_activities)
    ):
        raise ValueError("incomplete footprints must retain unknown negative facts")
    graph = model.reachability
    state_ids = set(range(len(graph.markings)))
    if len(graph.enabled_transition_ids) != len(graph.markings) or len(
        set(graph.markings)
    ) != len(graph.markings):
        raise ValueError("reachability states and enabling rows disagree")
    if graph.max_observed_tokens < 0 or graph.initial_admitted != bool(graph.markings):
        raise ValueError("invalid reachability admission or token count")
    if graph.final_state is not None and graph.final_state not in state_ids:
        raise ValueError("invalid reachability final state")
    if graph.complete != (graph.initial_admitted and not graph.boundary):
        raise ValueError("reachability completeness contradicts the boundary")
    successors = {}
    for edge in graph.edges:
        if (
            edge.source not in state_ids
            or edge.target not in state_ids
            or edge.transition_id not in graph.enabled_transition_ids[edge.source]
        ):
            raise ValueError("reachability edge lacks an admitted enabled endpoint")
        key = edge.source, edge.transition_id
        if key in successors:
            raise ValueError("duplicate reachability transition incidence")
        successors[key] = edge.target
    for boundary in graph.boundary:
        if (
            boundary.source not in state_ids
            or boundary.transition_id
            not in graph.enabled_transition_ids[boundary.source]
        ):
            raise ValueError("reachability boundary lacks an enabled source")
    expected_acceptance = (
        True if graph.final_state is not None else False if graph.complete else None
    )
    if model.accepted_language_exists is not expected_acceptance:
        raise ValueError("acceptance claim contradicts the final-state evidence")
    if model.minimum_length_proven and (
        model.minimum_trace_length is None or model.accepted_language_exists is not True
    ):
        raise ValueError("a proven minimum requires an accepting path")
    if model.accepts_empty_trace is True and model.accepted_language_exists is not True:
        raise ValueError("empty-trace acceptance requires an accepting language")
    if {
        (w.source_activity, w.target_activity) for w in model.relation_witnesses
    } != follows or len(model.relation_witnesses) != len(follows):
        raise ValueError("adjacency pairs require one corresponding supplied witness")
    for witness in model.relation_witnesses:
        state = witness.source_state
        for transition in (
            witness.first_transition_id,
            *witness.silent_transition_ids,
            witness.second_transition_id,
        ):
            if (state, transition) not in successors:
                raise ValueError(
                    "adjacency witness is not a path in supplied reachability"
                )
            state = successors[state, transition]
    if {w.activities for w in model.commuting_witnesses} != set(
        model.commuting_pairs
    ) or len(model.commuting_witnesses) != len(model.commuting_pairs):
        raise ValueError("commuting pairs require one corresponding supplied witness")
    for witness in model.commuting_witnesses:
        if (
            witness.source_state not in state_ids
            or len(set(witness.transition_ids)) != 2
            or not set(witness.transition_ids)
            <= set(graph.enabled_transition_ids[witness.source_state])
        ):
            raise ValueError(
                "commuting witness requires two distinct enabled transitions"
            )


def _model_footprints(model):
    """Keep incomplete negative facts unknown and commuting evidence separate."""
    _validate_model_footprints(model)
    follows, parallel = set(model.directly_follows), set(model.parallel)
    sequence = set(model.sequence or ())
    rows = []
    for left in model.declared_activities:
        for right in model.declared_activities:
            pair = left, right
            symbol = (
                "self"
                if left == right and pair in follows
                else "||"
                if pair in parallel
                else "->"
                if pair in sequence
                else "<-"
                if (right, left) in sequence
                else "follows"
                if pair in follows
                else "#"
                if model.complete
                else "?"
            )
            rows.append(
                MatrixCell(
                    left,
                    right,
                    symbol,
                    details=_details(
                        directly_follows=pair in follows, complete=model.complete
                    ),
                )
            )
    return (
        MatrixPanel(
            "model_footprints",
            "Executable model footprints",
            model.declared_activities,
            model.declared_activities,
            tuple(rows),
            legend=_details(
                **{
                    "->": "proven asymmetric adjacency",
                    "<-": "proven reverse asymmetric adjacency",
                    "||": "bidirectional adjacency, not itself concurrency",
                    "self": "self succession",
                    "follows": "witnessed adjacency; asymmetry unknown",
                    "#": "absent in completed exploration",
                    "?": "unknown under the search bound",
                }
            ),
            description=f"Behavior: {model.behavior}; complete: {model.complete}. Actual commuting transitions appear in their own witness table. The viewer checks internal consistency of supplied evidence; it does not re-execute the original model.",
        ),
        _table(
            "model_properties",
            "Model footprint properties",
            ("property", "value"),
            (
                (name, getattr(model, name))
                for name in (
                    "model_kind",
                    "model_digest",
                    "behavior",
                    "activities",
                    "inactive_activities",
                    "sequence",
                    "unrelated",
                    "start_activities",
                    "end_activities",
                    "accepts_empty_trace",
                    "accepted_language_exists",
                    "minimum_trace_length",
                    "minimum_length_proven",
                    "always_activities",
                    "complete",
                    "analysis_steps",
                )
            ),
            "Null properties remain unknown or undefined; an observed minimum is not proven unless minimum_length_proven is true.",
        ),
        _table(
            "relation_witnesses",
            "Adjacency witnesses",
            (
                "source",
                "target",
                "source_state",
                "first_transition_id",
                "silent_transition_ids",
                "second_transition_id",
            ),
            (
                (
                    w.source_activity,
                    w.target_activity,
                    w.source_state,
                    w.first_transition_id,
                    w.silent_transition_ids,
                    w.second_transition_id,
                )
                for w in model.relation_witnesses
            ),
        ),
        _table(
            "commuting_witnesses",
            "Actual commuting transition witnesses",
            ("source_state", "transition_ids", "activities", "common_target"),
            (
                (w.source_state, w.transition_ids, w.activities, w.common_target)
                for w in model.commuting_witnesses
            ),
            "These witnesses test two transition orders reaching one marking; they are distinct from symmetric activity adjacency.",
        ),
    )


def _declare(model):
    evidence = model.evidence or (None,) * len(model.rules)
    return (
        _table(
            "rules",
            "Declare constraints",
            (
                "template",
                "source",
                "target",
                "cardinality",
                "activated_cases",
                "satisfied_cases",
                "vacuous_cases",
                "support",
                "confidence",
            ),
            (
                (
                    r.template,
                    r.source,
                    r.target,
                    r.cardinality,
                    e.activated_cases if e else None,
                    e.satisfied_cases if e else None,
                    e.vacuous_cases if e else None,
                    e.support if e else None,
                    e.confidence if e else None,
                )
                for r, e in zip(model.rules, evidence)
            ),
            f"Profile: {model.profile}; case count: {model.case_count}.",
            "Response activates at source; precedence activates at target. A rule is a finite-trace constraint, not a sequence-flow arrow.",
            "Support is activated cases / all cases; confidence is satisfied / activated. Null denotes no supplied evidence or an undefined denominator.",
        ),
        _table(
            "alphabet",
            "Declared activity alphabet",
            ("activity",),
            ((a,) for a in model.activities),
        ),
    )


def _skeleton(model):
    return (
        _table(
            "relations",
            "Log skeleton relations",
            ("relation", "source", "target", "fulfilled", "eligible"),
            (
                (r.kind, r.source, r.target, r.fulfilled, r.eligible)
                for r in model.relations
            ),
            f"Profile: {model.profile}; cases: {model.case_count}; noise threshold: {model.noise_threshold}.",
            "Relations use their activation population; the table does not interpret them as executable control-flow arcs.",
        ),
        _table(
            "frequencies",
            "Per-case activity frequency domains",
            ("activity", "allowed_counts", "empirical_distribution"),
            (
                (f.activity, f.allowed_counts, f.distribution)
                for f in model.activity_frequencies
            ),
            "Distribution entries are (event count in one case, number of cases); zero counts remain explicit.",
        ),
    )


def _temporal(model):
    return (
        _table(
            "temporal",
            "Temporal profile",
            ("source", "target", "count", "mean", "standard_deviation"),
            (
                (e.source, e.target, e.count, e.mean, e.standard_deviation)
                for e in model.entries
            ),
            f"Relation: {model.spec.relation}; unit: {model.spec.time_unit}; ddof: {model.spec.ddof}.",
            f"Cases: {model.case_count}; observed pairs: {model.observed_pairs}; excluded missing: {model.excluded_missing}; excluded negative: {model.excluded_negative}.",
            "Rows summarize occurrence pairs. Null standard deviation is unknown, not zero.",
        ),
        _table(
            "temporal_policy",
            "Temporal population and timestamp policy",
            ("field", "value"),
            asdict(model.spec).items(),
        ),
    )


def _causal(model):
    nodes, edges = [], []
    ids = {t.id: _id("transition", t.id) for t in model.transitions}
    channels = {c.id: _id("channel", c.id) for c in model.channels}
    for t in model.transitions:
        nodes.append(
            _node(
                ids[t.id],
                "τ" if t.activity is None else t.activity,
                "silent" if t.activity is None else "transition",
                model_id=t.id,
            )
        )
    for c in model.channels:
        initial = tuple(
            t.object_id for t in model.initial_marking.tokens if t.place_id == c.id
        )
        final = tuple(
            t.object_id for t in model.final_marking.tokens if t.place_id == c.id
        )
        nodes.append(
            _node(
                channels[c.id],
                c.id,
                "channel",
                model_id=c.id,
                object_type=c.object_type,
                source_transition=c.source_transition,
                target_transition=c.target_transition,
                external_source=c.source_transition is None,
                external_sink=c.target_transition is None,
                initial_tokens=initial,
                final_tokens=final,
                initial_count=len(initial),
                final_count=len(final),
            )
        )
    groups = []
    for direction, bindings in (
        ("input", model.input_bindings),
        ("output", model.output_bindings),
    ):
        for binding in bindings:
            identifier = _id("group", binding.id)
            nodes.append(
                _node(
                    identifier,
                    binding.id,
                    "binding",
                    model_id=binding.id,
                    direction=direction,
                    transition_id=binding.transition_id,
                    equal_channels=binding.equal_channels,
                    disjoint_channels=binding.disjoint_channels,
                    empty=not binding.markers,
                )
            )
            source, target = (
                (identifier, ids[binding.transition_id])
                if direction == "input"
                else (ids[binding.transition_id], identifier)
            )
            edges.append(
                _edge(
                    _id("owner", identifier),
                    source,
                    target,
                    "choose alternative",
                    "binding",
                )
            )
            for marker in binding.markers:
                source, target = (
                    (channels[marker.channel_id], identifier)
                    if direction == "input"
                    else (identifier, channels[marker.channel_id])
                )
                upper = "∞" if marker.max_objects is None else str(marker.max_objects)
                edges.append(
                    _edge(
                        _id("marker", identifier, marker.channel_id),
                        source,
                        target,
                        f"{marker.min_objects}..{upper}",
                        "marker",
                        min_objects=marker.min_objects,
                        max_objects=marker.max_objects,
                        channel_id=marker.channel_id,
                    )
                )
            groups.append(
                (
                    direction,
                    binding.id,
                    binding.transition_id,
                    binding.markers,
                    binding.equal_channels,
                    binding.disjoint_channels,
                )
            )
    return (
        _graph(
            "model",
            "Object-centric causal net",
            nodes,
            edges,
            "A binding group is one AND alternative; one input and one output alternative are selected for a firing. Empty alternatives are explicit.",
            "Channels carry typed object obligations. Equality and disjointness constrain selected object sets; absent constraints do not imply disjointness.",
            "External channel endpoints and repeated marking tokens are preserved.",
        ),
        _table(
            "bindings",
            "Binding alternatives and identity constraints",
            (
                "direction",
                "group_id",
                "transition_id",
                "markers",
                "equal_channels",
                "disjoint_channels",
            ),
            groups,
        ),
        _table(
            "objects",
            "Declared object universe",
            ("object_id", "object_type"),
            model.objects,
        ),
    )


def _saw(model):
    return (
        *_pn(model.model),
        _table(
            "saw_distributions",
            "Empirical stochastic arc weights",
            (
                "source",
                "target",
                "transition_id",
                "object_type",
                "sample_basis",
                "histogram",
                "sample_count",
                "witness_indices",
                "expected_weight",
            ),
            (
                (
                    d.source,
                    d.target,
                    d.transition_id,
                    d.object_type,
                    d.sample_basis,
                    d.histogram,
                    d.sample_count,
                    d.witness_indices,
                    str(d.expected_weight) if d.expected_weight is not None else None,
                )
                for d in model.arc_distributions
            ),
            "Histogram entries are (distinct bound-object count, sample frequency); no samples means an unknown distribution.",
            "Shared witness indices preserve correlated observations. Marginals are not multiplied into a joint distribution; observed cardinality intervals do not add histogram support.",
        ),
        _table(
            "saw_witness",
            "Joint fitting witness",
            ("index", "step"),
            enumerate(model.discovery.fitting_witness),
        ),
        _table(
            "saw_policy",
            "Stochastic profile",
            ("field", "value"),
            (
                ("profile", model.profile),
                ("probability_scope", model.probability_scope),
                ("joint_probability_policy", model.joint_probability_policy),
                ("silent_sampling_policy", model.silent_sampling_policy),
            ),
        ),
    )


def _data_petri(model):
    rows = []
    for point in model.decisions:
        if not point.guards:
            rows.append((point.place_id, None, point.status, None, None, "unknown"))
        for guard in point.guards:
            clauses = tuple(
                tuple(asdict(c) for c in clause.conditions) for clause in guard.clauses
            )
            expression = (
                " OR ".join(
                    "("
                    + (
                        " AND ".join(
                            f"{c.feature_name} {c.operator} {c.threshold}"
                            for c in clause.conditions
                        )
                        or "true"
                    )
                    + ")"
                    for clause in guard.clauses
                )
                or "false"
            )
            rows.append(
                (
                    point.place_id,
                    guard.transition_id,
                    point.status,
                    guard.support,
                    clauses,
                    expression,
                )
            )
    return (
        *_pn(model.base),
        _table(
            "guards",
            "Data Petri net guards",
            (
                "decision_place",
                "transition_id",
                "status",
                "support",
                "dnf_clauses",
                "expression",
            ),
            rows,
            "Each guard is OR of AND clauses; an empty clause is true and no clauses is false. Guards from different decision places are conjoined.",
            "Untrained decisions evaluate unknown. Missing feature values are not zero. Expressions are display text, never executed.",
        ),
        _table(
            "features",
            "Typed decision feature schema",
            ("name", "definition"),
            ((f.name, f) for f in model.features),
        ),
        _table(
            "decision_evidence",
            "Decision training evidence",
            (
                "place_id",
                "transition_ids",
                "training_row_ids",
                "training_case_ids",
                "tree",
            ),
            (
                (
                    p.place_id,
                    p.transition_ids,
                    p.training_row_ids,
                    p.training_case_ids,
                    p.tree,
                )
                for p in model.decisions
            ),
        ),
    )


def model_panels(value):
    """Return native model panels, or None only for an unsupported input type.

    Supported inputs are checked through the strict model codec, including
    older relational dataclasses without constructor guards. Invalid supported
    models raise rather than publishing a plausible but incorrect graph.
    """
    if type(value) is ModelFootprints:
        return _model_footprints(value)
    if type(value) not in _SUPPORTED:
        return None
    validated = model_from_json(model_json_bytes(value)).model
    if validated != value:
        raise ValueError("visual model input must preserve its native model contract")
    dispatch = {
        PetriNet: _pn,
        ObjectCentricPetriNet: _pn,
        ProcessTree: _tree,
        POWLNode: _tree,
        SplitBPMN: _bpmn,
        TransitionSystem: _transition_system,
        FootprintModel: _footprints,
        HeuristicsNet: _heuristics,
        DeclareModel: _declare,
        LogSkeleton: _skeleton,
        TemporalProfile: _temporal,
        ObjectCentricCausalNet: _causal,
        StochasticArcWeightNet: _saw,
        DataPetriNet: _data_petri,
    }
    return dispatch[type(value)](value)


__all__ = ("model_panels",)
